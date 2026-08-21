"""EPIC-M1.81: ensure this platform's recommendation feed can eventually
present only predictions where the evidence supports a positive
investment opportunity, while preserving every candidate -- passed or
suppressed -- internally for measurement and learning.

M1.9/M1.13's own qualification already ensures every `Prediction` row
was, at generation time, a positive (upward-trending) opportunity that
cleared `app.consensus.MIN_CONFIDENCE` -- re-checking that same threshold
here would be redundant, not a second, independent check. This gate's
real, non-redundant contribution is requiring every *later-computed*
trust/evidence signal this platform has built since generation time to
ALSO independently pass: M1.74's per-prediction evidence-quality state,
M1.77's blended trust quality, M1.79's segment-specific trust (where
computed), and M1.80's model-level calibration drift (where computed).
"Prevent weak positive-looking predictions from passing through due to a
single metric" (scope) is enforced by requiring ALL checks to pass (AND,
never OR) -- a prediction cannot buy its way past a real weakness by
looking good on just one signal.

M1.74 (`evidence_quality_met`) and M1.77 (`trust_quality_met`) are
per-prediction signals this gate treats as REQUIRED: if neither has been
computed yet for this prediction, the gate honestly suppresses rather
than assuming the best. M1.79 (`segment_trust_met`) and M1.80
(`calibration_drift_met`) are cohort-level signals that will not always
have been computed for every specific `(model_version, horizon_days,
regime)` combination or model version yet; this gate treats them as
OPTIONAL -- checked and enforced only when available, never silently
ignored when they *are* available and failing, but also never blocking
a prediction purely because a cohort-level signal hasn't been computed
yet (an honest, forward-compatible choice, not a loophole: any signal
that *has* been computed and fails still suppresses).

Execution Rule: "positive-only is a presentation/recommendation policy,
not a learning-data deletion policy." This module has no write path to
`Prediction`, `ScanCandidate`, `RecommendationSelection`, or any other
production table -- a suppressed prediction is never deleted, hidden
from outcome measurement, or excluded from any learning pipeline; it is
only marked `GATE_SUPPRESSED` in this module's own, separate decision
log. Wiring this decision into the actual live recommendation feed is a
future EPIC's job (M1.84, "Trust-Driven Learning & Recommendation
Control" -- listed as this EPIC's own "Next" dependency), consistent
with the propose/gate split M1.65/M1.74/M1.77/M1.79/M1.80 already
established: none of those are wired into `app.target_stop_loss`'s
publish gate either.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .confidence_quality import QUALITY_HIGH, QUALITY_MEDIUM
from .evidence_quality_gate import STATE_SUFFICIENT, get_quality_decision_history
from .horizon_regime_trust import SEGMENT_COMBINED, get_latest_trust
from .market_regime import classify_market_regime
from .models import PositiveRecommendationGateDecision, Prediction, RecommendationGeneration, ScanCandidate
from .prediction_calibration_drift import get_drift_history
from .prediction_trust_score import get_trust_score_history

POSITIVE_GATE_VERSION = "PRG-001"

VERDICT_GATE_PASS = "GATE_PASS"
VERDICT_GATE_SUPPRESSED = "GATE_SUPPRESSED"

REASON_EVIDENCE_QUALITY_NOT_SUFFICIENT = "EVIDENCE_QUALITY_NOT_SUFFICIENT"
REASON_TRUST_QUALITY_TOO_LOW = "TRUST_QUALITY_TOO_LOW"
REASON_SEGMENT_LOW_TRUST = "SEGMENT_LOW_TRUST"
REASON_CALIBRATION_DRIFT_DETECTED = "CALIBRATION_DRIFT_DETECTED"

_ACCEPTABLE_TRUST_QUALITIES = (QUALITY_HIGH, QUALITY_MEDIUM)


class PositiveRecommendationGateDecisionImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "verdict",
    "evidence_quality_met",
    "trust_quality_met",
    "segment_trust_met",
    "calibration_drift_met",
    "suppression_reasons",
    "evaluated_at",
    "gate_rule_version",
    "created_at",
)


@event.listens_for(PositiveRecommendationGateDecision, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise PositiveRecommendationGateDecisionImmutableError(
            f"positive recommendation gate decision {target.id} field(s) {changed} cannot be modified after creation"
        )


def _evidence_quality_met(session: Session, prediction_id: int) -> bool:
    history = get_quality_decision_history(session, prediction_id)
    if not history:
        return False
    return history[-1].state == STATE_SUFFICIENT


def _trust_quality_met(session: Session, prediction_id: int) -> bool:
    history = get_trust_score_history(session, prediction_id)
    if not history:
        return False
    return history[-1].trust_quality in _ACCEPTABLE_TRUST_QUALITIES


def _regime_for_prediction(session: Session, prediction: Prediction) -> str | None:
    scan_id = session.execute(
        select(ScanCandidate.scan_id)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalar_one_or_none()
    if scan_id is None:
        return None
    return classify_market_regime(session, scan_id).regime


def _segment_trust_met(session: Session, prediction: Prediction) -> bool:
    """Optional: only enforced when a M1.79 COMBINED segment has
    actually been computed for this prediction's own
    `(model_version, horizon_days, regime)` cohort."""
    regime = _regime_for_prediction(session, prediction)
    if regime is None:
        return True
    segment = get_latest_trust(
        session, model_version=prediction.model_version, segment_type=SEGMENT_COMBINED,
        horizon_days=prediction.horizon_days, regime=regime,
    )
    if segment is None:
        return True
    return not segment.is_low_trust


def _calibration_drift_met(session: Session, prediction: Prediction) -> bool:
    """Optional: only enforced when a M1.80 drift check has actually
    been computed for this prediction's model version."""
    history = get_drift_history(session, prediction.model_version)
    if not history:
        return True
    return not history[-1].trust_reduction_recommended


def evaluate_positive_gate(
    session: Session, prediction: Prediction, *, evaluated_at: datetime
) -> PositiveRecommendationGateDecision:
    """Idempotent by `(prediction_id, evaluated_at)`. Every individual
    check is persisted so no single metric can be mistaken for the whole
    picture (AC: "prevent weak positive-looking predictions from passing
    through due to a single metric")."""
    existing = session.scalar(
        select(PositiveRecommendationGateDecision).where(
            PositiveRecommendationGateDecision.prediction_id == prediction.id,
            PositiveRecommendationGateDecision.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    evidence_quality_met = _evidence_quality_met(session, prediction.id)
    trust_quality_met = _trust_quality_met(session, prediction.id)
    segment_trust_met = _segment_trust_met(session, prediction)
    calibration_drift_met = _calibration_drift_met(session, prediction)

    reasons = []
    if not evidence_quality_met:
        reasons.append(REASON_EVIDENCE_QUALITY_NOT_SUFFICIENT)
    if not trust_quality_met:
        reasons.append(REASON_TRUST_QUALITY_TOO_LOW)
    if not segment_trust_met:
        reasons.append(REASON_SEGMENT_LOW_TRUST)
    if not calibration_drift_met:
        reasons.append(REASON_CALIBRATION_DRIFT_DETECTED)

    verdict = VERDICT_GATE_PASS if not reasons else VERDICT_GATE_SUPPRESSED

    decision = PositiveRecommendationGateDecision(
        prediction_id=prediction.id,
        verdict=verdict,
        evidence_quality_met=evidence_quality_met,
        trust_quality_met=trust_quality_met,
        segment_trust_met=segment_trust_met,
        calibration_drift_met=calibration_drift_met,
        suppression_reasons=reasons,
        evaluated_at=evaluated_at,
        gate_rule_version=POSITIVE_GATE_VERSION,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def get_gate_decision_history(session: Session, prediction_id: int) -> tuple[PositiveRecommendationGateDecision, ...]:
    return tuple(
        session.scalars(
            select(PositiveRecommendationGateDecision)
            .where(PositiveRecommendationGateDecision.prediction_id == prediction_id)
            .order_by(PositiveRecommendationGateDecision.id.asc())
        ).all()
    )
