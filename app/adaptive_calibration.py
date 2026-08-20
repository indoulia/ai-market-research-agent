"""EPIC-M1.29: use completed recommendation outcomes to measure and propose a
calibration adjustment for `predicted_probability`, and test that proposal
strictly out-of-sample against the current (unadjusted) calibration -- never
changing any production score automatically (non-goal: "automatic production
model replacement"). Promoting a candidate is explicitly out of scope for
this EPIC (that is M1.31's job, once it exists); this module only measures
and proposes.

Reuses M1.6's ten fixed-width probability buckets and M1.23's calibration
verdict vocabulary (`OVERCONFIDENT`/`UNDERCONFIDENT`/`WELL_CALIBRATED`/
`INSUFFICIENT_SAMPLE`, and its `CALIBRATION_ERROR_MARGIN`) rather than
redefining either. Reuses M1.25's `EvaluationWindow`/
`OverlappingEvaluationWindowsError` so a calibration candidate's training
window and its out-of-sample evaluation window are the same disjoint-window
concept already established there.

Horizon segmentation (scope item 2's "by horizon") is fully covered -- every
qualified, evaluated `Prediction` has a `horizon_days`. Regime segmentation
("... and regime") is reported as a measurement only -- calibration error
per regime, via `MarketRegime` (M1.26) "where available" (that table is not
populated for every scan) -- the candidate's actual probability adjustment
is not regime- or horizon-conditional in this first version, only the
overall-bucket offset is; that is a documented scope simplification, not an
omission.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .confidence_analysis import (
    CALIBRATION_ERROR_MARGIN,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_OVERCONFIDENT,
    VERDICT_UNDERCONFIDENT,
    VERDICT_WELL_CALIBRATED,
)
from .models import MarketRegime, Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate
from .out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from .performance import PROBABILITY_BUCKET_COUNT, PROBABILITY_BUCKET_WIDTH
from .recommendations import VALID_HORIZON_DAYS
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

CALIBRATION_CANDIDATE_VERSION = "CAL-001"

VERDICT_IMPROVED = "IMPROVED"
VERDICT_NOT_IMPROVED = "NOT_IMPROVED"

# A candidate's mean absolute calibration error must fall below the current
# (unadjusted) error by at least this margin, on the out-of-sample window, to
# be called an improvement rather than noise. Fixed, documented, versioned.
IMPROVEMENT_MARGIN = Decimal("0.02")


@dataclass(frozen=True)
class BucketCalibration:
    lower: Decimal
    upper: Decimal
    sample_count: int
    average_predicted_probability: Decimal | None
    observed_success_rate: Decimal | None
    calibration_error: Decimal | None
    verdict: str


@dataclass(frozen=True)
class RegimeCalibrationMetric:
    regime: str
    sample_count: int
    average_predicted_probability: Decimal | None
    observed_success_rate: Decimal | None
    calibration_error: Decimal | None


@dataclass(frozen=True)
class HorizonCalibrationBuckets:
    horizon_days: int
    buckets: tuple[BucketCalibration, ...]


@dataclass(frozen=True)
class CalibrationCandidate:
    version: str
    training_window: EvaluationWindow
    buckets: tuple[BucketCalibration, ...]
    by_horizon: tuple[HorizonCalibrationBuckets, ...]
    by_regime: tuple[RegimeCalibrationMetric, ...]


@dataclass(frozen=True)
class CalibrationComparisonResult:
    version: str
    evaluation_window: EvaluationWindow
    evaluated_count: int
    raw_mean_absolute_error: Decimal | None
    candidate_mean_absolute_error: Decimal | None
    verdict: str


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _bucket_index(predicted_probability: Decimal) -> int:
    index = int(predicted_probability / PROBABILITY_BUCKET_WIDTH)
    return min(index, PROBABILITY_BUCKET_COUNT - 1)


def _calibration_verdict(sample_count: int, calibration_error: Decimal | None) -> str:
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or calibration_error is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if calibration_error >= CALIBRATION_ERROR_MARGIN:
        return VERDICT_OVERCONFIDENT
    if calibration_error <= -CALIBRATION_ERROR_MARGIN:
        return VERDICT_UNDERCONFIDENT
    return VERDICT_WELL_CALIBRATED


def _evaluated_in_window(session: Session, window: EvaluationWindow) -> list[tuple[Prediction, PredictionOutcome]]:
    query = select(Prediction, PredictionOutcome).join(
        PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id
    ).where(PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    return list(session.execute(query).all())


def _windows_overlap(a: EvaluationWindow, b: EvaluationWindow) -> bool:
    if a.end is not None and b.start is not None and a.end < b.start:
        return False
    if b.end is not None and a.start is not None and b.end < a.start:
        return False
    return True


def _bucket_calibration(evaluated: list[tuple[Prediction, PredictionOutcome]]) -> tuple[BucketCalibration, ...]:
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
            BucketCalibration(
                lower=lower,
                upper=upper,
                sample_count=len(subset),
                average_predicted_probability=average_predicted,
                observed_success_rate=observed_rate,
                calibration_error=calibration_error,
                verdict=_calibration_verdict(len(subset), calibration_error),
            )
        )
    return tuple(buckets)


def _regime_calibration(session: Session, evaluated: list[tuple[Prediction, PredictionOutcome]]) -> tuple[RegimeCalibrationMetric, ...]:
    if not evaluated:
        return ()
    prediction_ids = [p.id for p, _ in evaluated]
    outcome_by_id = {p.id: o for p, o in evaluated}
    prediction_by_id = {p.id: p for p, _ in evaluated}

    rows = session.execute(
        select(RecommendationGeneration.prediction_id, MarketRegime.regime)
        .join(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
        .join(MarketRegime, MarketRegime.scan_id == ScanCandidate.scan_id)
        .where(RecommendationGeneration.prediction_id.in_(prediction_ids))
    ).all()

    by_regime: dict[str, list[int]] = {}
    for prediction_id, regime in rows:
        by_regime.setdefault(regime, []).append(prediction_id)

    metrics = []
    for regime in sorted(by_regime):
        ids = by_regime[regime]
        outcomes = [outcome_by_id[pid] for pid in ids]
        predictions = [prediction_by_id[pid] for pid in ids]
        success_count = sum(1 for o in outcomes if o.outcome == "SUCCESS")
        observed_rate = Decimal(success_count) / Decimal(len(outcomes)) if outcomes else None
        average_predicted = _mean([p.predicted_probability for p in predictions])
        calibration_error = (
            average_predicted - observed_rate if average_predicted is not None and observed_rate is not None else None
        )
        metrics.append(
            RegimeCalibrationMetric(
                regime=regime,
                sample_count=len(outcomes),
                average_predicted_probability=average_predicted,
                observed_success_rate=observed_rate,
                calibration_error=calibration_error,
            )
        )
    return tuple(metrics)


def build_calibration_candidate(session: Session, training_window: EvaluationWindow) -> CalibrationCandidate:
    """Derive a per-bucket calibration candidate from `training_window`'s
    closed outcomes only (scope item 1: "calibration uses only closed
    outcomes"). Original `Prediction.predicted_probability` values are never
    written to -- this returns a new, separate object (scope: "preserve
    original recommendation scores unchanged")."""
    evaluated = _evaluated_in_window(session, training_window)
    by_horizon = tuple(
        HorizonCalibrationBuckets(
            horizon_days=horizon_days,
            buckets=_bucket_calibration([(p, o) for p, o in evaluated if p.horizon_days == horizon_days]),
        )
        for horizon_days in VALID_HORIZON_DAYS
    )
    return CalibrationCandidate(
        version=CALIBRATION_CANDIDATE_VERSION,
        training_window=training_window,
        buckets=_bucket_calibration(evaluated),
        by_horizon=by_horizon,
        by_regime=_regime_calibration(session, evaluated),
    )


def apply_calibration_candidate(candidate: CalibrationCandidate, predicted_probability: Decimal) -> Decimal:
    """Pure function: returns an adjusted probability, never mutates
    anything. Falls back to the unadjusted value for a bucket without enough
    training-window evidence to trust an offset."""
    bucket = candidate.buckets[_bucket_index(predicted_probability)]
    if bucket.calibration_error is None or bucket.verdict == VERDICT_INSUFFICIENT_SAMPLE:
        return predicted_probability
    adjusted = predicted_probability - bucket.calibration_error
    return max(Decimal("0"), min(Decimal("1"), adjusted))


def evaluate_calibration_candidate_out_of_sample(
    session: Session, candidate: CalibrationCandidate, evaluation_window: EvaluationWindow
) -> CalibrationComparisonResult:
    """Compare the candidate's calibration error against the raw, unadjusted
    error on a strictly disjoint out-of-sample window (scope item 5, AC:
    "candidate calibration can be compared with current calibration
    out-of-sample"). Raises `OverlappingEvaluationWindowsError` if
    `evaluation_window` overlaps the candidate's own training window -- an
    out-of-sample test must never reuse training evidence."""
    if _windows_overlap(candidate.training_window, evaluation_window):
        raise OverlappingEvaluationWindowsError(
            f"evaluation window '{evaluation_window.label}' overlaps the candidate's "
            f"training window '{candidate.training_window.label}'"
        )

    evaluated = _evaluated_in_window(session, evaluation_window)
    if len(evaluated) < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        return CalibrationComparisonResult(
            version=CALIBRATION_CANDIDATE_VERSION,
            evaluation_window=evaluation_window,
            evaluated_count=len(evaluated),
            raw_mean_absolute_error=None,
            candidate_mean_absolute_error=None,
            verdict=VERDICT_INSUFFICIENT_SAMPLE,
        )

    raw_errors = []
    candidate_errors = []
    for prediction, outcome in evaluated:
        actual = Decimal("1") if outcome.outcome == "SUCCESS" else Decimal("0")
        raw_errors.append(abs(prediction.predicted_probability - actual))
        adjusted = apply_calibration_candidate(candidate, prediction.predicted_probability)
        candidate_errors.append(abs(adjusted - actual))

    raw_mae = _mean(raw_errors)
    candidate_mae = _mean(candidate_errors)
    verdict = VERDICT_IMPROVED if candidate_mae <= raw_mae - IMPROVEMENT_MARGIN else VERDICT_NOT_IMPROVED

    return CalibrationComparisonResult(
        version=CALIBRATION_CANDIDATE_VERSION,
        evaluation_window=evaluation_window,
        evaluated_count=len(evaluated),
        raw_mean_absolute_error=raw_mae,
        candidate_mean_absolute_error=candidate_mae,
        verdict=verdict,
    )
