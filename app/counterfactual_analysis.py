"""EPIC-M1.111: measure what would have happened to qualified candidates
that were never selected/published, so this platform can distinguish
true selection skill from merely avoiding difficult cases.

**Evaluate published versus suppressed candidates using identical
outcome definitions** (scope): `backfill_counterfactual_outcomes` calls
M1.5's own `evaluate_recommendation` completely unchanged -- that
function only needs `entry_price`/`target_return`/`stop_return`/
`horizon_days` plus subsequent `MarketPrice` rows, and never checks
whether the prediction was ever selected/published. Every real, already-
qualified `Prediction` this platform has ever made -- selected or not --
can therefore be evaluated by the exact same rule real published
recommendations already use. A candidate that never reached
`OUTCOME_QUALIFIED` at all (M1.13) has no `entry_price`/`target_return`/
`stop_return` to evaluate against in the first place -- that half of
"qualified and suppressed candidates" (scope) is honestly out of reach
without inventing a synthetic target/stop this platform never actually
proposed, and is named here rather than fabricated.

**Preserve point-in-time candidate universe and selection decisions**
(scope) holds because this module never writes to `RecommendationGeneration`,
`RecommendationSelection`, or `PositiveRecommendationGateDecision` --
only to `PredictionOutcome`, and only via M1.5's own immutable,
idempotent (`RecommendationAlreadyEvaluatedError`-guarded) writer.

**Compare ranking and gating alternatives** (scope) is already covered
by M1.99's `RankingEffectivenessReport` and is not duplicated here.

**Measure opportunity cost and avoided losses / feed counterfactual
evidence into discovery/ranking evaluation without changing historical
decisions:** `compare_published_vs_suppressed` is a read-only, always-
fresh report (the same posture as M1.85/M1.99/M1.102/M1.108/M1.109) --
`opportunity_cost_total` sums the realized gain on suppressed candidates
that would have succeeded; `avoided_loss_total` sums the realized loss
on suppressed candidates that would have failed. Neither number is ever
written back into any selection/gating/ranking table.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Prediction, PredictionOutcome, PublishedVsSuppressedReport, RecommendationGeneration, RecommendationSelection, ScanCandidate
from .out_of_sample_validation import EvaluationWindow
from .outcomes import RecommendationAlreadyEvaluatedError, evaluate_recommendation
from .recommendation_generator import OUTCOME_QUALIFIED
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK, WEAKNESS_MARGIN

COUNTERFACTUAL_ANALYSIS_VERSION = "CFA-001"


def backfill_counterfactual_outcomes(session: Session, scan_id: int) -> tuple[PredictionOutcome, ...]:
    """For every M1.13-qualified generation in `scan_id` whose `Prediction`
    has no `PredictionOutcome` yet -- selected or not -- evaluates it now
    via M1.5's own, unmodified `evaluate_recommendation`. Skips (rather
    than fails) a prediction whose horizon hasn't elapsed enough trading
    days yet, or one already evaluated by an earlier call."""
    prediction_ids = session.scalars(
        select(RecommendationGeneration.prediction_id)
        .join(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
        .where(
            ScanCandidate.scan_id == scan_id, RecommendationGeneration.outcome == OUTCOME_QUALIFIED,
            RecommendationGeneration.prediction_id.isnot(None),
        )
    ).all()

    new_outcomes: list[PredictionOutcome] = []
    for prediction_id in prediction_ids:
        prediction = session.get(Prediction, prediction_id)
        if prediction is None:
            continue
        try:
            outcome = evaluate_recommendation(session, prediction)
        except RecommendationAlreadyEvaluatedError:
            continue
        if outcome is not None:
            new_outcomes.append(outcome)
    return tuple(new_outcomes)


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _qualified_outcome_rows(session: Session, window: EvaluationWindow) -> list[tuple[PredictionOutcome, bool]]:
    """Returns (outcome, was_selected) for every M1.13-qualified prediction
    with a real, already-evaluated outcome within `window`."""
    query = (
        select(PredictionOutcome, RecommendationSelection.selected)
        .select_from(RecommendationGeneration)
        .join(Prediction, Prediction.id == RecommendationGeneration.prediction_id)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .outerjoin(RecommendationSelection, RecommendationSelection.recommendation_generation_id == RecommendationGeneration.id)
        .where(RecommendationGeneration.outcome == OUTCOME_QUALIFIED, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    )
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    rows = session.execute(query).all()
    return [(outcome, bool(selected)) for outcome, selected in rows]


def compare_published_vs_suppressed(session: Session, *, window: EvaluationWindow, computed_at: datetime) -> PublishedVsSuppressedReport:
    """Always computes and persists a fresh, independent report row."""
    rows = _qualified_outcome_rows(session, window)
    published = [outcome for outcome, selected in rows if selected]
    suppressed = [outcome for outcome, selected in rows if not selected]

    published_sample_count = len(published)
    suppressed_sample_count = len(suppressed)
    published_success_count = sum(1 for o in published if o.outcome == "SUCCESS")
    suppressed_success_count = sum(1 for o in suppressed if o.outcome == "SUCCESS")
    published_success_rate = _rate(published_success_count, published_sample_count)
    suppressed_success_rate = _rate(suppressed_success_count, suppressed_sample_count)

    opportunity_cost_total = sum(
        (o.actual_return for o in suppressed if o.outcome == "SUCCESS"), Decimal("0")
    )
    avoided_loss_total = sum(
        (abs(o.actual_return) for o in suppressed if o.outcome == "FAILURE"), Decimal("0")
    )

    if (
        published_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or suppressed_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or published_success_rate is None
        or suppressed_success_rate is None
    ):
        verdict = VERDICT_INSUFFICIENT_SAMPLE
        success_rate_delta = None
    else:
        success_rate_delta = published_success_rate - suppressed_success_rate
        verdict = VERDICT_OK if success_rate_delta >= WEAKNESS_MARGIN else VERDICT_WEAK

    report = PublishedVsSuppressedReport(
        window_label=window.label, published_sample_count=published_sample_count,
        published_success_count=published_success_count, published_success_rate=published_success_rate,
        suppressed_sample_count=suppressed_sample_count, suppressed_success_count=suppressed_success_count,
        suppressed_success_rate=suppressed_success_rate, success_rate_delta=success_rate_delta,
        opportunity_cost_total=opportunity_cost_total, avoided_loss_total=avoided_loss_total, verdict=verdict,
        computed_at=computed_at, report_rule_version=COUNTERFACTUAL_ANALYSIS_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_counterfactual_report_history(session: Session) -> tuple[PublishedVsSuppressedReport, ...]:
    return tuple(session.scalars(select(PublishedVsSuppressedReport).order_by(PublishedVsSuppressedReport.id.asc())).all())
