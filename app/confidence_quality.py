"""EPIC-M1.50: tell users how trustworthy a confidence percentage is, by
combining M1.49's calibration quality and sample size with M1.35's data
freshness -- deliberately never as a function of the raw confidence value
itself (AC: "a high confidence with weak evidence cannot receive HIGH
quality"; "confidence quality is separate from prediction confidence").

Composes rather than duplicates: M1.49's `ConfidenceCalibrationRecord`
(calibration verdict, sample count -- doubling as the "comparable historical
setup count" scope item, since that count *is* the number of bucket-matched
historical outcomes the calibration was built from) and M1.35's
`check_market_data_freshness` (data freshness/completeness). No new
evidence-gathering logic is introduced; this module only classifies
evidence M1.49/M1.35 already produced.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .confidence_analysis import VERDICT_INSUFFICIENT_SAMPLE, VERDICT_WELL_CALIBRATED
from .confidence_calibration import ConfidenceCalibrationRecord
from .models import ConfidenceQualityClassification, Prediction
from .refresh_policy import check_market_data_freshness
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

CONFIDENCE_QUALITY_VERSION = "CFQ-001"

QUALITY_HIGH = "HIGH"
QUALITY_MEDIUM = "MEDIUM"
QUALITY_LOW = "LOW"
QUALITY_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

# A "strong" comparable-historical-setup count, as opposed to merely
# "adequate" (M1.16's own floor). Fixed, documented, versioned -- not learned.
STRONG_SAMPLE_MULTIPLIER = 2


class ConfidenceQualityImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "confidence_calibration_record_id",
    "quality",
    "reasons",
    "sample_count",
    "calibration_verdict",
    "is_data_fresh",
    "classified_at",
    "classification_rule_version",
    "created_at",
)


@event.listens_for(ConfidenceQualityClassification, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise ConfidenceQualityImmutableError(
            f"confidence quality classification {target.id} field(s) {changed} cannot be modified after creation"
        )


def get_confidence_quality(
    session: Session, prediction_id: int, *, classification_rule_version: str = CONFIDENCE_QUALITY_VERSION
) -> ConfidenceQualityClassification | None:
    return session.scalar(
        select(ConfidenceQualityClassification).where(
            ConfidenceQualityClassification.prediction_id == prediction_id,
            ConfidenceQualityClassification.classification_rule_version == classification_rule_version,
        )
    )


def classify_confidence_quality(
    session: Session,
    prediction: Prediction,
    calibration_record: ConfidenceCalibrationRecord,
    *,
    classified_at: datetime,
    classification_rule_version: str = CONFIDENCE_QUALITY_VERSION,
) -> ConfidenceQualityClassification:
    """Deterministic classification of `prediction.confidence`'s
    trustworthiness (AC: "quality calculation is deterministic and
    versioned") -- never a function of `prediction.confidence`'s own value
    (AC). Idempotent by `(prediction_id, classification_rule_version)`."""
    existing = get_confidence_quality(session, prediction.id, classification_rule_version=classification_rule_version)
    if existing is not None:
        return existing

    reasons: list[str] = []

    if calibration_record.verdict == VERDICT_INSUFFICIENT_SAMPLE:
        reasons.append(
            f"comparable historical setup count ({calibration_record.sample_count}) is below the minimum "
            f"of {MIN_SAMPLE_SIZE_FOR_COMPARISON} required to trust this confidence bucket's calibration"
        )
        quality = QUALITY_INSUFFICIENT_DATA
        is_fresh = False
    else:
        is_well_calibrated = calibration_record.verdict == VERDICT_WELL_CALIBRATED
        reasons.append(
            f"calibration verdict is {calibration_record.verdict} "
            f"(calibration_error={calibration_record.calibration_error})"
        )

        is_strong_sample = calibration_record.sample_count >= MIN_SAMPLE_SIZE_FOR_COMPARISON * STRONG_SAMPLE_MULTIPLIER
        reasons.append(
            f"comparable historical setup count is {calibration_record.sample_count} "
            f"({'strong' if is_strong_sample else 'adequate'} evidence)"
        )

        freshness = check_market_data_freshness(session, prediction.stock_id, prediction.as_of_timestamp)
        is_fresh = freshness.is_fresh
        reasons.append(
            f"underlying market data is {'fresh' if is_fresh else (freshness.reason or 'stale')}"
        )

        if is_well_calibrated and is_strong_sample and is_fresh:
            quality = QUALITY_HIGH
        elif is_well_calibrated and is_fresh:
            quality = QUALITY_MEDIUM
        else:
            quality = QUALITY_LOW

    classification = ConfidenceQualityClassification(
        prediction_id=prediction.id,
        confidence_calibration_record_id=calibration_record.id,
        quality=quality,
        reasons=reasons,
        sample_count=calibration_record.sample_count,
        calibration_verdict=calibration_record.verdict,
        is_data_fresh=is_fresh,
        classified_at=classified_at,
        classification_rule_version=classification_rule_version,
    )
    session.add(classification)
    session.commit()
    session.refresh(classification)
    return classification
