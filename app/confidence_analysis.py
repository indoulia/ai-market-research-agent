"""EPIC-M1.23: measure whether M1.13's reported `predicted_probability` actually
corresponds to realized M1.5 outcomes -- true calibration (does a bucket
predicting ~70% succeed ~70% of the time?), distinct from M1.16's trust report
(which flags a segment performing *below the platform's overall rate*, not
against its own stated probability). Read-only, deterministic, versioned, and
never rewrites a historical `Prediction.predicted_probability` value.

Reuses M1.6's ten fixed-width probability buckets (`PROBABILITY_BUCKET_COUNT`/
`PROBABILITY_BUCKET_WIDTH`) and M1.16's minimum-sample-size policy constant
(`MIN_SAMPLE_SIZE_FOR_COMPARISON`) rather than defining new ones for the same
underlying bucketing/reliability questions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Prediction, PredictionOutcome
from .performance import PROBABILITY_BUCKET_COUNT, PROBABILITY_BUCKET_WIDTH
from .recommendations import VALID_HORIZON_DAYS
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

CONFIDENCE_ANALYSIS_VERSION = "CFA-001"

# A predicted-vs-observed gap at or beyond this margin, with sufficient sample
# support, is flagged as a real calibration problem rather than noise. Fixed
# product/policy constant, bumped via CONFIDENCE_ANALYSIS_VERSION if changed.
CALIBRATION_ERROR_MARGIN = Decimal("0.10")

VERDICT_OVERCONFIDENT = "OVERCONFIDENT"
VERDICT_UNDERCONFIDENT = "UNDERCONFIDENT"
VERDICT_WELL_CALIBRATED = "WELL_CALIBRATED"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


@dataclass(frozen=True)
class ProbabilityBucketCalibration:
    bucket_label: str
    lower: Decimal
    upper: Decimal
    evaluated_count: int
    average_predicted_probability: Decimal | None
    observed_success_rate: Decimal | None
    calibration_error: Decimal | None
    verdict: str


@dataclass(frozen=True)
class HorizonCalibration:
    horizon_days: int
    buckets: tuple[ProbabilityBucketCalibration, ...]


@dataclass(frozen=True)
class ConfidenceAnalysisReport:
    report_version: str
    evaluated_count: int
    overall_buckets: tuple[ProbabilityBucketCalibration, ...]
    by_horizon: tuple[HorizonCalibration, ...]


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _bucket_index(predicted_probability: Decimal) -> int:
    index = int(predicted_probability / PROBABILITY_BUCKET_WIDTH)
    return min(index, PROBABILITY_BUCKET_COUNT - 1)


def _calibration_verdict(sample_count: int, calibration_error: Decimal | None) -> str:
    """"Persistent" over/under-confidence (scope item 3) means a gap that
    clears the same minimum-sample floor M1.16 uses for "is this segment's
    rate reliable evidence" -- a gap on a handful of samples is noise, not a
    persistent pattern."""
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or calibration_error is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if calibration_error >= CALIBRATION_ERROR_MARGIN:
        return VERDICT_OVERCONFIDENT
    if calibration_error <= -CALIBRATION_ERROR_MARGIN:
        return VERDICT_UNDERCONFIDENT
    return VERDICT_WELL_CALIBRATED


def _bucket_breakdown(evaluated: list[tuple[Prediction, PredictionOutcome]]) -> tuple[ProbabilityBucketCalibration, ...]:
    buckets = []
    for index in range(PROBABILITY_BUCKET_COUNT):
        lower = PROBABILITY_BUCKET_WIDTH * index
        upper = PROBABILITY_BUCKET_WIDTH * (index + 1)
        subset = [(p, o) for p, o in evaluated if _bucket_index(p.predicted_probability) == index]
        success_count = sum(1 for _, o in subset if o.outcome == "SUCCESS")
        observed_rate = Decimal(success_count) / Decimal(len(subset)) if subset else None
        average_predicted = _mean([p.predicted_probability for p, _ in subset])
        calibration_error = (
            average_predicted - observed_rate if average_predicted is not None and observed_rate is not None else None
        )
        buckets.append(
            ProbabilityBucketCalibration(
                bucket_label=f"[{lower}, {upper}{']' if index == PROBABILITY_BUCKET_COUNT - 1 else ')'}",
                lower=lower,
                upper=upper,
                evaluated_count=len(subset),
                average_predicted_probability=average_predicted,
                observed_success_rate=observed_rate,
                calibration_error=calibration_error,
                verdict=_calibration_verdict(len(subset), calibration_error),
            )
        )
    return tuple(buckets)


def compute_confidence_analysis_report(session: Session) -> ConfidenceAnalysisReport:
    """Every statistic is a plain deterministic aggregate over stored
    `Prediction`/`PredictionOutcome` rows (scope item 6); `open`/`unevaluable`
    recommendations are excluded from calibration (there is no realized
    success/failure to compare a probability against) but this module writes
    to nothing, so `Prediction.predicted_probability` is preserved unchanged
    regardless (scope item 7)."""
    rows = session.execute(
        select(Prediction, PredictionOutcome).join(
            PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id, isouter=True
        )
    ).all()

    evaluated = [(p, o) for p, o in rows if o is not None and o.outcome in ("SUCCESS", "FAILURE")]

    overall_buckets = _bucket_breakdown(evaluated)
    by_horizon = tuple(
        HorizonCalibration(
            horizon_days=horizon_days,
            buckets=_bucket_breakdown([(p, o) for p, o in evaluated if p.horizon_days == horizon_days]),
        )
        for horizon_days in VALID_HORIZON_DAYS
    )

    return ConfidenceAnalysisReport(
        report_version=CONFIDENCE_ANALYSIS_VERSION,
        evaluated_count=len(evaluated),
        overall_buckets=overall_buckets,
        by_horizon=by_horizon,
    )
