"""EPIC-M1.11: measure whether stated recommendation probabilities correspond to
observed success rates, using only M1.5's objectively evaluated outcomes (M1.6's
bucketing philosophy). Does not retrain any model, does not change historical
recommendations, and does not touch the M1.8 consensus criteria (all non-goals) --
this EPIC only measures calibration; acting on it is future work.
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Prediction, PredictionOutcome
from .performance import PROBABILITY_BUCKET_COUNT, PROBABILITY_BUCKET_WIDTH
from .recommendations import VALID_HORIZON_DAYS

CALIBRATION_VERSION = "CAL-001"

# A bucket's calibration statistic is only presented as reliable once at least this
# many objectively evaluated recommendations fall in it; below this, "insufficient
# sample" is reported explicitly instead of a number that looks precise but isn't.
MIN_SAMPLE_SIZE = 30

# A |observed - predicted| gap at or above this is material enough to flag the bucket
# as under/overconfident rather than "well calibrated". Fixed, documented threshold --
# not learned/optimized from historical outcomes.
MATERIAL_ERROR_THRESHOLD = Decimal("0.10")

INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
OVERCONFIDENT = "OVERCONFIDENT"
UNDERCONFIDENT = "UNDERCONFIDENT"
WELL_CALIBRATED = "WELL_CALIBRATED"


@dataclass(frozen=True)
class CalibrationBucket:
    bucket_label: str
    lower: Decimal
    upper: Decimal
    sample_size: int
    predicted_probability: Decimal | None
    observed_success_rate: Decimal | None
    calibration_error: Decimal | None
    assessment: str


@dataclass(frozen=True)
class HorizonCalibration:
    horizon_days: int
    buckets: tuple[CalibrationBucket, ...]


@dataclass(frozen=True)
class CalibrationReport:
    calibration_version: str
    overall: tuple[CalibrationBucket, ...]
    by_horizon: tuple[HorizonCalibration, ...]


def _bucket_index(predicted_probability: Decimal) -> int:
    index = int(predicted_probability / PROBABILITY_BUCKET_WIDTH)
    return min(index, PROBABILITY_BUCKET_COUNT - 1)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _bucketize(evaluated: list[tuple[Prediction, PredictionOutcome]]) -> tuple[CalibrationBucket, ...]:
    buckets = []
    for index in range(PROBABILITY_BUCKET_COUNT):
        lower = PROBABILITY_BUCKET_WIDTH * index
        upper = PROBABILITY_BUCKET_WIDTH * (index + 1)
        subset = [(p, o) for p, o in evaluated if _bucket_index(p.predicted_probability) == index]
        sample_size = len(subset)

        predicted = _mean([p.predicted_probability for p, _ in subset])
        success_count = sum(1 for _, o in subset if o.outcome == "SUCCESS")
        observed = Decimal(success_count) / Decimal(sample_size) if sample_size else None

        if sample_size < MIN_SAMPLE_SIZE:
            error = None
            assessment = INSUFFICIENT_SAMPLE
        else:
            error = observed - predicted
            if error >= MATERIAL_ERROR_THRESHOLD:
                assessment = UNDERCONFIDENT  # actual success rate materially exceeds the stated probability
            elif error <= -MATERIAL_ERROR_THRESHOLD:
                assessment = OVERCONFIDENT  # actual success rate materially falls short of the stated probability
            else:
                assessment = WELL_CALIBRATED

        buckets.append(CalibrationBucket(
            bucket_label=f"[{lower}, {upper}{']' if index == PROBABILITY_BUCKET_COUNT - 1 else ')'}",
            lower=lower,
            upper=upper,
            sample_size=sample_size,
            predicted_probability=predicted,
            observed_success_rate=observed,
            calibration_error=error,
            assessment=assessment,
        ))
    return tuple(buckets)


def compute_calibration_report(session: Session) -> CalibrationReport:
    """Historical predictions are never rewritten by this report -- it only reads
    `Prediction`/`PredictionOutcome` rows, both already immutable (M1.4/M1.5)."""
    rows = session.execute(
        select(Prediction, PredictionOutcome)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .where(PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    ).all()
    evaluated = [(p, o) for p, o in rows]

    overall = _bucketize(evaluated)
    by_horizon = tuple(
        HorizonCalibration(
            horizon_days=horizon_days,
            buckets=_bucketize([(p, o) for p, o in evaluated if p.horizon_days == horizon_days]),
        )
        for horizon_days in VALID_HORIZON_DAYS
    )

    return CalibrationReport(
        calibration_version=CALIBRATION_VERSION,
        overall=overall,
        by_horizon=by_horizon,
    )
