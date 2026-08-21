"""EPIC-M1.77: a dedicated, evidence-backed Prediction Trust Score that
measures how trustworthy a prediction is, separately from its score and
calibrated probability.

Every component is a read-only lookup into a signal an earlier EPIC
already computed -- this module never recomputes calibration, regime
performance, model regression, or evidence quality itself, only combines
already-produced evidence (AC: "trust must be earned from out-of-sample
evidence"; Execution Rule: never increase trust merely because a model
was retrained or a prediction was revised -- there is no code path here
that reads anything about retraining/revision recency at all).

Scope names three distinct dimensions -- "recent performance," "model
stability," and "drift signals" -- that this platform currently has only
ONE real, independently-computed signal for: M1.67's `ModelRegressionCheck`
(a model's own real-world performance holding steady vs. regressing over
time *is* this platform's current notion of stability/drift). Rather than
inventing two more numbers from the same source to look more thorough,
`recent_performance_component` alone represents all three until a future
EPIC (e.g. a dedicated stability/agreement measure) adds a genuinely
independent signal -- an honest, forward-compatible choice, the same
posture M1.35 took with `DATA_TYPE_FUNDAMENTAL`/`DATA_TYPE_NEWS_EVENT`
before real ingestion existed for them.

"Sample size" (scope) is not folded into the weighted average -- it
gates `trust_quality` independently via `available_component_count`, so
a high average built from only one or two available components can never
reach `QUALITY_HIGH` (AC: "insufficient evidence reduces trust or
produces an explicit insufficient-data state").
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .confidence_quality import QUALITY_HIGH, QUALITY_INSUFFICIENT_DATA, QUALITY_LOW, QUALITY_MEDIUM, get_confidence_quality
from .evidence_quality_gate import STATE_INSUFFICIENT, STATE_LEAKAGE_DETECTED, STATE_SUFFICIENT, get_quality_decision_history
from .market_regime import classify_market_regime
from .model_regression_detection import VERDICT_HEALTHY, VERDICT_REGRESSED, get_regression_history
from .models import Prediction, PredictionOutcome, PredictionTrustScore, RecommendationGeneration, ScanCandidate
from .out_of_sample_validation import EvaluationWindow
from .regime_aware_scoring import VERDICT_INSUFFICIENT_SAMPLE as REGIME_VERDICT_INSUFFICIENT_SAMPLE, analyze_regime_performance
from .short_horizon_probability import VERDICT_CALIBRATED, get_latest_probability_profile
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

PREDICTION_TRUST_SCORE_VERSION = "PTS-001"

# Six independent evidence sources feed the average; a leaked evidence
# snapshot (M1.74 STATE_LEAKAGE_DETECTED) is a hard override to
# QUALITY_INSUFFICIENT_DATA regardless of any other component.
TOTAL_COMPONENTS = 6

# Fixed, documented, versioned: a majority of the six components must be
# available before trust_quality can reach QUALITY_HIGH/QUALITY_MEDIUM on
# their own average alone -- otherwise it is capped, however good the
# few available numbers look (AC: "insufficient evidence reduces trust").
MIN_AVAILABLE_COMPONENTS_FOR_FULL_TRUST = 4

REASON_EVIDENCE_LEAKAGE_DETECTED = "EVIDENCE_LEAKAGE_DETECTED"
REASON_NO_COMPONENTS_AVAILABLE = "NO_COMPONENTS_AVAILABLE"
REASON_TOO_FEW_COMPONENTS_AVAILABLE = "TOO_FEW_COMPONENTS_AVAILABLE"

_CONFIDENCE_QUALITY_TO_SCORE = {
    QUALITY_HIGH: Decimal("1"),
    QUALITY_MEDIUM: Decimal("0.6"),
    QUALITY_LOW: Decimal("0.3"),
}


class PredictionTrustScoreImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "overall_trust_score",
    "trust_quality",
    "calibration_component",
    "historical_accuracy_component",
    "recent_performance_component",
    "horizon_reliability_component",
    "regime_reliability_component",
    "evidence_quality_component",
    "available_component_count",
    "reasons",
    "computed_at",
    "trust_score_version",
    "created_at",
)


@event.listens_for(PredictionTrustScore, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise PredictionTrustScoreImmutableError(
            f"prediction trust score {target.id} field(s) {changed} cannot be modified after creation"
        )


def _calibration_component(session: Session, prediction: Prediction) -> Decimal | None:
    classification = get_confidence_quality(session, prediction.id)
    if classification is None:
        return None
    return _CONFIDENCE_QUALITY_TO_SCORE.get(classification.quality)


def _historical_accuracy_component(session: Session, model_version: str) -> Decimal | None:
    rows = session.execute(
        select(PredictionOutcome.outcome)
        .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
        .where(Prediction.model_version == model_version, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    ).all()
    if len(rows) < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        return None
    success_count = sum(1 for (outcome,) in rows if outcome == "SUCCESS")
    return Decimal(success_count) / Decimal(len(rows))


def _recent_performance_component(session: Session, model_version: str) -> Decimal | None:
    history = get_regression_history(session, model_version)
    if not history:
        return None
    latest = history[-1]
    if latest.verdict == VERDICT_HEALTHY:
        return Decimal("1")
    if latest.verdict == VERDICT_REGRESSED:
        return Decimal("0")
    return None


def _horizon_reliability_component(session: Session, prediction: Prediction) -> Decimal | None:
    profile = get_latest_probability_profile(session, model_version=prediction.model_version, horizon_days=prediction.horizon_days)
    if profile is None or profile.verdict != VERDICT_CALIBRATED:
        return None
    return profile.target_hit_probability


def _regime_for_prediction(session: Session, prediction: Prediction) -> str:
    scan_id = session.execute(
        select(ScanCandidate.scan_id)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalar_one()
    return classify_market_regime(session, scan_id).regime


def _regime_reliability_component(session: Session, prediction: Prediction) -> Decimal | None:
    regime = _regime_for_prediction(session, prediction)
    all_time = EvaluationWindow(label="all-time", start=None, end=None)
    performance = analyze_regime_performance(session, all_time)
    match = next((p for p in performance if p.regime == regime), None)
    if match is None or match.verdict == REGIME_VERDICT_INSUFFICIENT_SAMPLE:
        return None
    return match.observed_success_rate


def _evidence_quality_component(session: Session, prediction: Prediction) -> tuple[Decimal | None, bool]:
    """Returns (component, leakage_detected)."""
    history = get_quality_decision_history(session, prediction.id)
    if not history:
        return None, False
    latest = history[-1]
    if latest.state == STATE_LEAKAGE_DETECTED:
        return Decimal("0"), True
    if latest.state == STATE_SUFFICIENT:
        return Decimal("1"), False
    if latest.state == STATE_INSUFFICIENT:
        return Decimal("0"), False
    return None, False


def compute_prediction_trust_score(
    session: Session, prediction: Prediction, *, computed_at: datetime
) -> PredictionTrustScore:
    """Deterministic given the currently-available evidence from every
    composed module (AC: "every trust value is explainable and
    versioned"). Idempotent by `(prediction_id, computed_at)`; a later
    `computed_at` re-reads whichever dependencies have since produced new
    evidence (scope: "support daily recalculation as new outcomes become
    available") without this module ever triggering their computation
    itself."""
    existing = session.scalar(
        select(PredictionTrustScore).where(
            PredictionTrustScore.prediction_id == prediction.id, PredictionTrustScore.computed_at == computed_at
        )
    )
    if existing is not None:
        return existing

    evidence_quality_component, leakage_detected = _evidence_quality_component(session, prediction)

    reasons: list[str] = []

    if leakage_detected:
        score = PredictionTrustScore(
            prediction_id=prediction.id,
            overall_trust_score=None,
            trust_quality=QUALITY_INSUFFICIENT_DATA,
            calibration_component=None,
            historical_accuracy_component=None,
            recent_performance_component=None,
            horizon_reliability_component=None,
            regime_reliability_component=None,
            evidence_quality_component=evidence_quality_component,
            available_component_count=0,
            reasons=[REASON_EVIDENCE_LEAKAGE_DETECTED],
            computed_at=computed_at,
            trust_score_version=PREDICTION_TRUST_SCORE_VERSION,
        )
        session.add(score)
        session.commit()
        session.refresh(score)
        return score

    calibration_component = _calibration_component(session, prediction)
    historical_accuracy_component = _historical_accuracy_component(session, prediction.model_version)
    recent_performance_component = _recent_performance_component(session, prediction.model_version)
    horizon_reliability_component = _horizon_reliability_component(session, prediction)
    regime_reliability_component = _regime_reliability_component(session, prediction)

    components = [
        calibration_component,
        historical_accuracy_component,
        recent_performance_component,
        horizon_reliability_component,
        regime_reliability_component,
        evidence_quality_component,
    ]
    available = [c for c in components if c is not None]
    available_component_count = len(available)

    if not available:
        reasons.append(REASON_NO_COMPONENTS_AVAILABLE)
        overall_trust_score = None
        trust_quality = QUALITY_INSUFFICIENT_DATA
    else:
        overall_trust_score = sum(available) / Decimal(len(available))
        if available_component_count < MIN_AVAILABLE_COMPONENTS_FOR_FULL_TRUST:
            reasons.append(REASON_TOO_FEW_COMPONENTS_AVAILABLE)
            trust_quality = QUALITY_MEDIUM if overall_trust_score >= Decimal("0.5") else QUALITY_LOW
        elif overall_trust_score >= Decimal("0.75"):
            trust_quality = QUALITY_HIGH
        elif overall_trust_score >= Decimal("0.5"):
            trust_quality = QUALITY_MEDIUM
        else:
            trust_quality = QUALITY_LOW

    score = PredictionTrustScore(
        prediction_id=prediction.id,
        overall_trust_score=overall_trust_score,
        trust_quality=trust_quality,
        calibration_component=calibration_component,
        historical_accuracy_component=historical_accuracy_component,
        recent_performance_component=recent_performance_component,
        horizon_reliability_component=horizon_reliability_component,
        regime_reliability_component=regime_reliability_component,
        evidence_quality_component=evidence_quality_component,
        available_component_count=available_component_count,
        reasons=reasons,
        computed_at=computed_at,
        trust_score_version=PREDICTION_TRUST_SCORE_VERSION,
    )
    session.add(score)
    session.commit()
    session.refresh(score)
    return score


def get_trust_score_history(session: Session, prediction_id: int) -> tuple[PredictionTrustScore, ...]:
    return tuple(
        session.scalars(
            select(PredictionTrustScore)
            .where(PredictionTrustScore.prediction_id == prediction_id)
            .order_by(PredictionTrustScore.id.asc())
        ).all()
    )
