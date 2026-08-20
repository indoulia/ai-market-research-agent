"""EPIC-M1.49: make `Prediction.confidence` a calibrated probability grounded
in observed historical outcomes, rather than an unverified model score --
distinct from M1.23's `confidence_analysis` (which calibrates
`predicted_probability`, read-only, with no persisted per-prediction
record) and M1.29's `adaptive_calibration` (which also calibrates
`predicted_probability`, over disjoint windows, also without persisting a
per-prediction record).

Reuses M1.6's probability-bucket width (`app.performance`), M1.16's minimum-
sample-size floor, and M1.23's calibration verdict vocabulary and margin --
the same "is this bucket's evidence reliable, and is it biased" question,
applied to `confidence` instead of `predicted_probability`. Reuses M1.25's
`EvaluationWindow` for the training window a calibration draws its evidence
from.

Leakage control is structural, not conventional: `calibrate_confidence_for_
prediction` requires the training window to end strictly before the
prediction's own `as_of_timestamp`, and raises `FutureDataLeakageError`
otherwise -- there is no code path that can calibrate a prediction against
evidence that would not yet have existed when that prediction was made.

Raw and calibrated confidence are stored on separate columns
(`raw_confidence`/`calibrated_confidence`) on one immutable, versioned row
per `(prediction_id, calibration_version)` -- `Prediction.confidence` itself
is never written to.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .confidence_analysis import (
    CALIBRATION_ERROR_MARGIN,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_OVERCONFIDENT,
    VERDICT_UNDERCONFIDENT,
    VERDICT_WELL_CALIBRATED,
)
from .models import ConfidenceCalibrationRecord, Prediction, PredictionOutcome
from .out_of_sample_validation import EvaluationWindow
from .performance import PROBABILITY_BUCKET_COUNT, PROBABILITY_BUCKET_WIDTH
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

CONFIDENCE_CALIBRATION_VERSION = "CFC-001"


class FutureDataLeakageError(RuntimeError):
    pass


class ConfidenceCalibrationImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "calibration_version",
    "raw_confidence",
    "calibrated_confidence",
    "bucket_lower",
    "bucket_upper",
    "sample_count",
    "calibration_error",
    "verdict",
    "training_window_label",
    "calibrated_at",
    "created_at",
)


@event.listens_for(ConfidenceCalibrationRecord, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise ConfidenceCalibrationImmutableError(
            f"confidence calibration record {target.id} field(s) {changed} cannot be modified after creation"
        )


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _bucket_index(confidence: Decimal) -> int:
    index = int(confidence / PROBABILITY_BUCKET_WIDTH)
    return min(index, PROBABILITY_BUCKET_COUNT - 1)


def _bucket_bounds(index: int) -> tuple[Decimal, Decimal]:
    return PROBABILITY_BUCKET_WIDTH * index, PROBABILITY_BUCKET_WIDTH * (index + 1)


def _verdict(sample_count: int, calibration_error: Decimal | None) -> str:
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or calibration_error is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if calibration_error >= CALIBRATION_ERROR_MARGIN:
        return VERDICT_OVERCONFIDENT
    if calibration_error <= -CALIBRATION_ERROR_MARGIN:
        return VERDICT_UNDERCONFIDENT
    return VERDICT_WELL_CALIBRATED


def _evaluated_in_window_and_bucket(
    session: Session, window: EvaluationWindow, bucket_index: int
) -> list[tuple[Prediction, PredictionOutcome]]:
    query = select(Prediction, PredictionOutcome).join(
        PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id
    ).where(PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    rows = session.execute(query).all()
    return [(p, o) for p, o in rows if _bucket_index(p.confidence) == bucket_index]


def get_confidence_calibration(
    session: Session, prediction_id: int, *, calibration_version: str = CONFIDENCE_CALIBRATION_VERSION
) -> ConfidenceCalibrationRecord | None:
    return session.scalar(
        select(ConfidenceCalibrationRecord).where(
            ConfidenceCalibrationRecord.prediction_id == prediction_id,
            ConfidenceCalibrationRecord.calibration_version == calibration_version,
        )
    )


def calibrate_confidence_for_prediction(
    session: Session,
    prediction: Prediction,
    *,
    training_window: EvaluationWindow,
    calibrated_at: datetime,
    calibration_version: str = CONFIDENCE_CALIBRATION_VERSION,
) -> ConfidenceCalibrationRecord:
    """Calibrate `prediction.confidence` against the bucket of already-closed
    outcomes sharing its confidence bucket, from `training_window` (AC:
    "calibration uses only eligible historical outcomes"). Idempotent by
    `(prediction_id, calibration_version)` -- deterministic and reproducible
    (AC) for the same inputs and version. Raises `FutureDataLeakageError` if
    `training_window` could include evidence that would not yet have
    existed when `prediction` was made (AC: "calibration avoids future-data
    leakage")."""
    existing = get_confidence_calibration(session, prediction.id, calibration_version=calibration_version)
    if existing is not None:
        return existing

    # sqlite drops tzinfo on DateTime(timezone=True) round-trips, unlike
    # Postgres; every timestamp in this system is UTC-based by convention, so
    # comparing naively is correct regardless of which backend produced it.
    if training_window.end is None or (
        training_window.end.replace(tzinfo=None) >= prediction.as_of_timestamp.replace(tzinfo=None)
    ):
        raise FutureDataLeakageError(
            f"training window '{training_window.label}' must end strictly before prediction "
            f"{prediction.id}'s as_of_timestamp ({prediction.as_of_timestamp}) to avoid leakage"
        )

    bucket_index = _bucket_index(prediction.confidence)
    lower, upper = _bucket_bounds(bucket_index)
    evaluated = _evaluated_in_window_and_bucket(session, training_window, bucket_index)

    sample_count = len(evaluated)
    success_count = sum(1 for _, o in evaluated if o.outcome == "SUCCESS")
    observed_rate = Decimal(success_count) / Decimal(sample_count) if sample_count else None
    average_confidence = _mean([p.confidence for p, _ in evaluated])
    calibration_error = (
        average_confidence - observed_rate if average_confidence is not None and observed_rate is not None else None
    )
    verdict = _verdict(sample_count, calibration_error)
    calibrated_confidence = observed_rate if verdict != VERDICT_INSUFFICIENT_SAMPLE else None

    record = ConfidenceCalibrationRecord(
        prediction_id=prediction.id,
        calibration_version=calibration_version,
        raw_confidence=prediction.confidence,
        calibrated_confidence=calibrated_confidence,
        bucket_lower=lower,
        bucket_upper=upper,
        sample_count=sample_count,
        calibration_error=calibration_error,
        verdict=verdict,
        training_window_label=training_window.label,
        calibrated_at=calibrated_at,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
