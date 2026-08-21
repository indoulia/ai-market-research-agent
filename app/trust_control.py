"""EPIC-M1.84: close the trust feedback loop so measured prediction
performance controls recommendation eligibility, learning, and
recalibration -- without ever allowing an unsupported confidence
increase.

This is the final consolidation step over five already-built, purely
read-only "propose, never apply" signals -- it introduces no new
measurement of its own, only combines what M1.77/M1.79/M1.80/M1.82/M1.83
already computed:

- M1.77 `PredictionTrustScore.trust_quality` (the blended composite).
- M1.79 `HorizonRegimeTrust` for this prediction's own `(model_version,
  horizon_days, regime)` `COMBINED` segment, where computed.
- M1.80 `PredictionCalibrationDrift.trust_reduction_recommended` for this
  prediction's model version, where computed.
- M1.82 `PredictionQualityBenchmarkReport.trust_reduction_recommended`
  for this prediction's model version, where computed.
- M1.83 `PredictionStabilityAssessment.trust_reduction_recommended` for
  this prediction's own revision lineage, where computed.

"Deterioration can automatically reduce positive recommendation
eligibility" (AC) is realized as `eligibility_reduced` -- a *signal*,
not an enforcement action. Consistent with M1.65/M1.74/M1.77/M1.79/M1.80/
M1.81/M1.82/M1.83's own established posture, this module has no write
path to `Prediction`, `ScanCandidate`, or `RecommendationSelection` --
wiring `eligibility_reduced` into the live recommendation feed (M1.14's
`select_recommendations_for_scan`) is deliberately left to a future
deployment/operational step, matching this EPIC's own "Next: Continuous
operational validation" (not another numbered EPIC).

"Trigger evidence-backed recalibration, replay, candidate evaluation or
revalidation when thresholds are breached" (scope) is realized as
`recommended_action` -- naming which *existing* remedial mechanism
applies (M1.62's revalidation, M1.29/M1.49's recalibration, or M1.30/
M1.43/M1.44's candidate comparison/promotion gate), never re-implementing
or bypassing any of them. "Coordinate with existing model comparison and
promotion gates" therefore means exactly this: point at the correct
existing gate, never duplicate its logic.

"Improvement requires validated out-of-sample evidence" (AC) holds
structurally, not by a special case here: every one of the five composed
signals is itself computed fresh from currently-available, already
out-of-sample-validated evidence each time it runs (M1.77 explicitly
never reads anything about retraining/revision recency; M1.83's
stability signal requires a real successful outcome, never stability
alone) -- this module cannot inflate trust by re-running with no new
evidence, because it never computes anything itself, only reads.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .confidence_quality import QUALITY_HIGH, QUALITY_INSUFFICIENT_DATA, QUALITY_MEDIUM
from .horizon_regime_trust import SEGMENT_COMBINED, get_latest_trust
from .market_regime import classify_market_regime
from .models import Prediction, RecommendationGeneration, ScanCandidate, TrustControlDecision
from .prediction_calibration_drift import get_drift_history
from .prediction_quality_benchmark import get_benchmark_report_history
from .prediction_stability import get_stability_history
from .prediction_trust_score import get_trust_score_history

TRUST_CONTROL_VERSION = "TCL-001"

CAUSE_LOW_TRUST_QUALITY = "LOW_TRUST_QUALITY"
CAUSE_SEGMENT_LOW_TRUST = "SEGMENT_LOW_TRUST"
CAUSE_CALIBRATION_DRIFT = "CALIBRATION_DRIFT"
CAUSE_BENCHMARK_UNDERPERFORMANCE = "BENCHMARK_UNDERPERFORMANCE"
CAUSE_INSTABILITY = "INSTABILITY"

ACTION_NONE = "NONE"
ACTION_TRIGGER_REVALIDATION = "TRIGGER_REVALIDATION"
ACTION_TRIGGER_RECALIBRATION = "TRIGGER_RECALIBRATION"
ACTION_TRIGGER_MODEL_COMPARISON = "TRIGGER_MODEL_COMPARISON"

_ACCEPTABLE_TRUST_QUALITIES = (QUALITY_HIGH, QUALITY_MEDIUM)


class TrustControlDecisionImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "overall_trust_quality",
    "eligibility_reduced",
    "segment_trust_ok",
    "calibration_drift_ok",
    "benchmark_performance_ok",
    "stability_ok",
    "causes",
    "recommended_action",
    "evaluated_at",
    "control_rule_version",
    "created_at",
)


@event.listens_for(TrustControlDecision, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise TrustControlDecisionImmutableError(
            f"trust control decision {target.id} field(s) {changed} cannot be modified after creation"
        )


def _overall_trust_quality(session: Session, prediction_id: int) -> str:
    history = get_trust_score_history(session, prediction_id)
    if not history:
        return QUALITY_INSUFFICIENT_DATA
    return history[-1].trust_quality


def _regime_for_prediction(session: Session, prediction: Prediction) -> str | None:
    scan_id = session.execute(
        select(ScanCandidate.scan_id)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalar_one_or_none()
    if scan_id is None:
        return None
    return classify_market_regime(session, scan_id).regime


def _segment_trust_ok(session: Session, prediction: Prediction) -> bool:
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


def _calibration_drift_ok(session: Session, model_version: str) -> bool:
    history = get_drift_history(session, model_version)
    if not history:
        return True
    return not history[-1].trust_reduction_recommended


def _benchmark_performance_ok(session: Session, model_version: str) -> bool:
    history = get_benchmark_report_history(session, model_version)
    if not history:
        return True
    return not history[-1].trust_reduction_recommended


def _stability_ok(session: Session, prediction_id: int) -> bool:
    history = get_stability_history(session, prediction_id)
    if not history:
        return True
    return not history[-1].trust_reduction_recommended


def evaluate_trust_control(
    session: Session, prediction: Prediction, *, evaluated_at: datetime
) -> TrustControlDecision:
    """Idempotent by `(prediction_id, evaluated_at)`. Purely a read-only
    consolidation over five already-computed signals -- never triggers
    any of them, never writes to `Prediction`."""
    existing = session.scalar(
        select(TrustControlDecision).where(
            TrustControlDecision.prediction_id == prediction.id, TrustControlDecision.evaluated_at == evaluated_at
        )
    )
    if existing is not None:
        return existing

    overall_trust_quality = _overall_trust_quality(session, prediction.id)
    segment_trust_ok = _segment_trust_ok(session, prediction)
    calibration_drift_ok = _calibration_drift_ok(session, prediction.model_version)
    benchmark_performance_ok = _benchmark_performance_ok(session, prediction.model_version)
    stability_ok = _stability_ok(session, prediction.id)

    causes = []
    if overall_trust_quality not in _ACCEPTABLE_TRUST_QUALITIES:
        causes.append(CAUSE_LOW_TRUST_QUALITY)
    if not segment_trust_ok:
        causes.append(CAUSE_SEGMENT_LOW_TRUST)
    if not calibration_drift_ok:
        causes.append(CAUSE_CALIBRATION_DRIFT)
    if not benchmark_performance_ok:
        causes.append(CAUSE_BENCHMARK_UNDERPERFORMANCE)
    if not stability_ok:
        causes.append(CAUSE_INSTABILITY)

    eligibility_reduced = bool(causes)

    if not eligibility_reduced:
        recommended_action = ACTION_NONE
    elif CAUSE_CALIBRATION_DRIFT in causes or CAUSE_BENCHMARK_UNDERPERFORMANCE in causes:
        recommended_action = ACTION_TRIGGER_MODEL_COMPARISON
    elif CAUSE_INSTABILITY in causes:
        recommended_action = ACTION_TRIGGER_REVALIDATION
    else:
        recommended_action = ACTION_TRIGGER_RECALIBRATION

    decision = TrustControlDecision(
        prediction_id=prediction.id,
        overall_trust_quality=overall_trust_quality,
        eligibility_reduced=eligibility_reduced,
        segment_trust_ok=segment_trust_ok,
        calibration_drift_ok=calibration_drift_ok,
        benchmark_performance_ok=benchmark_performance_ok,
        stability_ok=stability_ok,
        causes=causes,
        recommended_action=recommended_action,
        evaluated_at=evaluated_at,
        control_rule_version=TRUST_CONTROL_VERSION,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def get_control_decision_history(session: Session, prediction_id: int) -> tuple[TrustControlDecision, ...]:
    return tuple(
        session.scalars(
            select(TrustControlDecision)
            .where(TrustControlDecision.prediction_id == prediction_id)
            .order_by(TrustControlDecision.id.asc())
        ).all()
    )
