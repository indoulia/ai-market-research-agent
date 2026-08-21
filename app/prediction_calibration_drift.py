"""EPIC-M1.80: detect changes in prediction behavior and probability
calibration between two disjoint evaluation windows for one model
version, early enough to reduce trust before degraded predictions
materially damage recommendation quality.

Composes rather than duplicates M1.67's `detect_model_regression`: that
module already answers "has this model's own real-world *success rate*
degraded between two windows," and already segments that answer by
horizon and regime (scope item 3: "detect changes in outcome rates by
horizon and regime"). Reusing it here -- rather than re-deriving the
same segmentation -- is exactly this platform's established
"an EPIC whose title echoes an earlier one gets a new table but reuses
the earlier one's own logic where the question is identical" pattern.

This module's own, genuinely new contribution is two signals M1.67 does
not compute at all: **prediction-distribution drift** (has the raw
`predicted_probability` distribution itself shifted between windows,
independent of outcomes) and **calibration drift** (has the *gap*
between predicted probability and realized success rate widened between
windows -- a model can keep the same success rate while becoming
systematically over- or under-confident, which M1.67's success-rate-only
comparison would never catch).

"Feed confirmed drift into Trust and learning controls" (scope) is a
forward-compatible capability, not an enforcement this module performs:
`trust_reduction_recommended` is exposed for a future consumer (e.g.
M1.84) -- this module has no write path to `Prediction`, `ScanCandidate`,
or `PredictionTrustScore` itself, matching the platform's established
propose/gate split. Execution Rule: "detection is not proof of failure" --
drift is a signal, never an automatic model change.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .confidence_analysis import CALIBRATION_ERROR_MARGIN
from .model_regression_detection import VERDICT_REGRESSED, detect_model_regression
from .models import Prediction, PredictionCalibrationDrift, PredictionOutcome
from .out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

CALIBRATION_DRIFT_VERSION = "PCD-001"

VERDICT_DRIFT_DETECTED = "DRIFT_DETECTED"
VERDICT_NO_DRIFT = "NO_DRIFT"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

# Reused unchanged from M1.23's own calibration-gap threshold (scope:
# "avoid triggering on statistically insignificant noise") -- the same
# magnitude that already means "materially miscalibrated" within one
# window is used here as "materially shifted" between two windows.
DISTRIBUTION_DRIFT_MARGIN = CALIBRATION_ERROR_MARGIN


def _windows_overlap(a: EvaluationWindow, b: EvaluationWindow) -> bool:
    if a.end is not None and b.start is not None and a.end < b.start:
        return False
    if b.end is not None and a.start is not None and b.end < a.start:
        return False
    return True


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _evaluated_for_model_in_window(
    session: Session, model_version: str, window: EvaluationWindow
) -> list[tuple[Prediction, PredictionOutcome]]:
    query = select(Prediction, PredictionOutcome).join(
        PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id
    ).where(Prediction.model_version == model_version, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    return list(session.execute(query).all())


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values) / Decimal(len(values))


def detect_prediction_calibration_drift(
    session: Session,
    *,
    model_version: str,
    baseline_window: EvaluationWindow,
    monitoring_window: EvaluationWindow,
    checked_at: datetime,
) -> PredictionCalibrationDrift:
    """Baseline and monitoring windows must be versioned and disjoint
    (AC: "baselines and comparison windows are versioned"); raises
    `OverlappingEvaluationWindowsError` otherwise -- monitoring must
    never reuse baseline evidence. Below `MIN_SAMPLE_SIZE_FOR_COMPARISON`
    on either side, the verdict is explicitly `VERDICT_INSUFFICIENT_
    SAMPLE` (AC: "sample-size thresholds are enforced")."""
    if _windows_overlap(baseline_window, monitoring_window):
        raise OverlappingEvaluationWindowsError(
            f"baseline window '{baseline_window.label}' and monitoring window '{monitoring_window.label}' overlap"
        )

    baseline_rows = _evaluated_for_model_in_window(session, model_version, baseline_window)
    monitoring_rows = _evaluated_for_model_in_window(session, model_version, monitoring_window)
    baseline_sample_count = len(baseline_rows)
    monitoring_sample_count = len(monitoring_rows)

    regression_check = detect_model_regression(
        session, model_version=model_version, baseline_window=baseline_window,
        monitoring_window=monitoring_window, checked_at=checked_at,
    )

    if baseline_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or monitoring_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        drift = PredictionCalibrationDrift(
            model_version=model_version,
            baseline_window_label=baseline_window.label,
            baseline_sample_count=baseline_sample_count,
            monitoring_window_label=monitoring_window.label,
            monitoring_sample_count=monitoring_sample_count,
            baseline_mean_predicted_probability=None,
            monitoring_mean_predicted_probability=None,
            distribution_drift=None,
            distribution_drift_detected=False,
            baseline_calibration_error=None,
            monitoring_calibration_error=None,
            calibration_drift=None,
            calibration_drift_detected=False,
            model_regression_check_id=regression_check.id,
            verdict=VERDICT_INSUFFICIENT_SAMPLE,
            trust_reduction_recommended=False,
            checked_at=checked_at,
            drift_rule_version=CALIBRATION_DRIFT_VERSION,
        )
        session.add(drift)
        session.commit()
        session.refresh(drift)
        return drift

    baseline_predicted = [p.predicted_probability for p, _ in baseline_rows]
    monitoring_predicted = [p.predicted_probability for p, _ in monitoring_rows]
    baseline_mean_pp = _mean(baseline_predicted)
    monitoring_mean_pp = _mean(monitoring_predicted)
    distribution_drift = monitoring_mean_pp - baseline_mean_pp
    distribution_drift_detected = abs(distribution_drift) >= DISTRIBUTION_DRIFT_MARGIN

    baseline_success_rate = _rate(sum(1 for _, o in baseline_rows if o.outcome == "SUCCESS"), baseline_sample_count)
    monitoring_success_rate = _rate(sum(1 for _, o in monitoring_rows if o.outcome == "SUCCESS"), monitoring_sample_count)
    baseline_calibration_error = baseline_mean_pp - baseline_success_rate
    monitoring_calibration_error = monitoring_mean_pp - monitoring_success_rate
    calibration_drift = abs(monitoring_calibration_error) - abs(baseline_calibration_error)
    calibration_drift_detected = calibration_drift >= CALIBRATION_ERROR_MARGIN

    drift_detected = (
        distribution_drift_detected or calibration_drift_detected or regression_check.verdict == VERDICT_REGRESSED
    )
    verdict = VERDICT_DRIFT_DETECTED if drift_detected else VERDICT_NO_DRIFT

    drift = PredictionCalibrationDrift(
        model_version=model_version,
        baseline_window_label=baseline_window.label,
        baseline_sample_count=baseline_sample_count,
        monitoring_window_label=monitoring_window.label,
        monitoring_sample_count=monitoring_sample_count,
        baseline_mean_predicted_probability=baseline_mean_pp,
        monitoring_mean_predicted_probability=monitoring_mean_pp,
        distribution_drift=distribution_drift,
        distribution_drift_detected=distribution_drift_detected,
        baseline_calibration_error=baseline_calibration_error,
        monitoring_calibration_error=monitoring_calibration_error,
        calibration_drift=calibration_drift,
        calibration_drift_detected=calibration_drift_detected,
        model_regression_check_id=regression_check.id,
        verdict=verdict,
        trust_reduction_recommended=drift_detected,
        checked_at=checked_at,
        drift_rule_version=CALIBRATION_DRIFT_VERSION,
    )
    session.add(drift)
    session.commit()
    session.refresh(drift)
    return drift


def get_drift_history(session: Session, model_version: str) -> tuple[PredictionCalibrationDrift, ...]:
    return tuple(
        session.scalars(
            select(PredictionCalibrationDrift)
            .where(PredictionCalibrationDrift.model_version == model_version)
            .order_by(PredictionCalibrationDrift.id.asc())
        ).all()
    )
