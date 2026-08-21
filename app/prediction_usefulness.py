"""EPIC-M1.86: measure whether positive recommendations are genuinely
useful to an investor, not merely directionally correct.

M1.82's `PredictionQualityBenchmarkReport` already measures directional
accuracy, target/stop rates, expected-vs-realized return, excursion,
time-to-exit, and benchmark-relative excess return -- this module does
not recompute any of that. Its own, genuinely new contribution is
"distinguish directional correctness from investment usefulness"
(scope): a prediction can be `SUCCESS` (M1.5's own directional label)
while still being a poor investment outcome if the drawdown risked along
the way was as large as, or larger than, the gain realized. `risk_
adjusted_ratio = actual_return / abs(maximum_drawdown)` captures exactly
that -- a real, simple, well-known risk-adjusted measure, not a
fabricated score.

"Feed usefulness metrics into Trust Score and learning" (scope) is a
forward-compatible capability, not an enforcement this module performs:
this module has no write path to `Prediction`, `PredictionOutcome`, or
`PredictionTrustScore` itself -- consuming these metrics into M1.84's
already-merged trust-control decision is left to a future revision of
that module, exactly like every other propose-only signal in this
platform's trust chain.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import HorizonUsefulnessReport, Prediction, PredictionOutcome, PredictionUsefulnessAssessment
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

USEFULNESS_RULE_VERSION = "PUM-001"
USEFULNESS_REPORT_VERSION = "HUR-001"

USEFUL = "USEFUL"
DIRECTIONALLY_CORRECT_NOT_USEFUL = "DIRECTIONALLY_CORRECT_NOT_USEFUL"
NOT_USEFUL = "NOT_USEFUL"

REPORT_VERDICT_MEASURED = "MEASURED"
REPORT_VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

# Fixed, documented, versioned policy constant: the realized gain must be
# at least as large as the maximum drawdown risked along the way for a
# directionally-correct prediction to also count as investment-useful --
# not learned or fitted.
MIN_USEFUL_RISK_ADJUSTED_RATIO = Decimal("1.0")


class PredictionUsefulnessAssessmentImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "directional_outcome",
    "risk_adjusted_ratio",
    "usefulness_verdict",
    "assessed_at",
    "usefulness_rule_version",
    "created_at",
)


@event.listens_for(PredictionUsefulnessAssessment, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise PredictionUsefulnessAssessmentImmutableError(
            f"prediction usefulness assessment {target.id} field(s) {changed} cannot be modified after creation"
        )


def get_usefulness_assessment(session: Session, prediction_id: int) -> PredictionUsefulnessAssessment | None:
    return session.scalar(
        select(PredictionUsefulnessAssessment).where(PredictionUsefulnessAssessment.prediction_id == prediction_id)
    )


def _classify(directional_outcome: str, risk_adjusted_ratio: Decimal | None, zero_drawdown: bool) -> str:
    if directional_outcome != "SUCCESS":
        return NOT_USEFUL
    if zero_drawdown:
        return USEFUL
    if risk_adjusted_ratio is not None and risk_adjusted_ratio >= MIN_USEFUL_RISK_ADJUSTED_RATIO:
        return USEFUL
    return DIRECTIONALLY_CORRECT_NOT_USEFUL


def assess_prediction_usefulness(
    session: Session, prediction: Prediction, *, assessed_at: datetime
) -> PredictionUsefulnessAssessment | None:
    """Idempotent per `prediction_id` (AC: "preserve historical
    measurements immutably"). Returns `None` -- never fabricates an
    assessment -- for a prediction with no evaluated outcome yet."""
    existing = get_usefulness_assessment(session, prediction.id)
    if existing is not None:
        return existing

    outcome = session.scalar(select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction.id))
    if outcome is None or outcome.outcome not in ("SUCCESS", "FAILURE"):
        return None

    zero_drawdown = outcome.maximum_drawdown == 0
    risk_adjusted_ratio = None if zero_drawdown else outcome.actual_return / abs(outcome.maximum_drawdown)

    assessment = PredictionUsefulnessAssessment(
        prediction_id=prediction.id,
        directional_outcome=outcome.outcome,
        risk_adjusted_ratio=risk_adjusted_ratio,
        usefulness_verdict=_classify(outcome.outcome, risk_adjusted_ratio, zero_drawdown),
        assessed_at=assessed_at,
        usefulness_rule_version=USEFULNESS_RULE_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def compute_horizon_usefulness_report(
    session: Session, *, model_version: str, horizon_days: int, computed_at: datetime
) -> HorizonUsefulnessReport:
    """Ensures every evaluated prediction in this `(model_version,
    horizon_days)` cohort has a persisted usefulness assessment (AC:
    "every closed recommendation receives usefulness metrics where data
    permits"), then aggregates them. Below `MIN_SAMPLE_SIZE_FOR_
    COMPARISON`, explicitly `INSUFFICIENT_SAMPLE` (AC: "insufficient
    data is explicit"; "metrics are segmented by horizon")."""
    rows = session.execute(
        select(Prediction, PredictionOutcome)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .where(
            Prediction.model_version == model_version,
            Prediction.horizon_days == horizon_days,
            PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")),
        )
    ).all()

    assessments = [assess_prediction_usefulness(session, prediction, assessed_at=computed_at) for prediction, _ in rows]
    assessments = [a for a in assessments if a is not None]
    sample_count = len(assessments)

    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        report = HorizonUsefulnessReport(
            model_version=model_version, horizon_days=horizon_days, sample_count=sample_count,
            avg_risk_adjusted_ratio=None, useful_rate=None, verdict=REPORT_VERDICT_INSUFFICIENT_SAMPLE,
            computed_at=computed_at, report_rule_version=USEFULNESS_REPORT_VERSION,
        )
    else:
        ratios = [a.risk_adjusted_ratio for a in assessments if a.risk_adjusted_ratio is not None]
        avg_risk_adjusted_ratio = sum(ratios) / Decimal(len(ratios)) if ratios else None
        useful_count = sum(1 for a in assessments if a.usefulness_verdict == USEFUL)
        useful_rate = Decimal(useful_count) / Decimal(sample_count)
        report = HorizonUsefulnessReport(
            model_version=model_version, horizon_days=horizon_days, sample_count=sample_count,
            avg_risk_adjusted_ratio=avg_risk_adjusted_ratio, useful_rate=useful_rate, verdict=REPORT_VERDICT_MEASURED,
            computed_at=computed_at, report_rule_version=USEFULNESS_REPORT_VERSION,
        )

    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_usefulness_report_history(session: Session, *, model_version: str, horizon_days: int) -> tuple[HorizonUsefulnessReport, ...]:
    return tuple(
        session.scalars(
            select(HorizonUsefulnessReport)
            .where(HorizonUsefulnessReport.model_version == model_version, HorizonUsefulnessReport.horizon_days == horizon_days)
            .order_by(HorizonUsefulnessReport.id.asc())
        ).all()
    )
