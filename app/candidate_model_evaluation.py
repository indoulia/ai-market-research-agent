"""EPIC-M1.30: evaluate a candidate scoring/prediction model against the
current production model using strictly time-separated historical data.

This repo still has no second, real candidate model to compare against
production -- the identical caveat M1.25 and M1.29 already documented. What
this EPIC builds, genuinely usable today, is the comprehensive comparison
machinery two disjoint historical windows need: success rate, realized and
predicted return, calibration error, and horizon/sector/market-cap/discovery-
source/regime segmentation, all computed identically for both windows and
compared side by side. Once a real second model exists, "baseline window"
and "candidate window" become "baseline model's period" and "candidate
model's period" with zero changes to this module.

Composes rather than duplicates where a windowed primitive already exists
(M1.25's `EvaluationWindow`/`OverlappingEvaluationWindowsError`, and the same
windowed-query pattern M1.25/M1.29 already established); the per-window,
multi-dimensional aggregation itself (return, calibration, horizon, sector/
market-cap via M1.34's `DiscoverySegment`, discovery source via M1.17's
`DiscoveryRecord`, regime via M1.26's `MarketRegime`, all "where available"
for the dimensions that aren't universally populated) is this EPIC's own new
contribution -- no existing report function is itself window-parameterized,
so extending each would have meant modifying several already-merged modules;
instead this module re-derives the windowed aggregate directly, the same
scoping choice M1.25/M1.29 already made.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    DiscoveryRecord,
    DiscoverySegment,
    MarketRegime,
    Prediction,
    PredictionOutcome,
    RecommendationGeneration,
    ScanCandidate,
)
from .out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from .recommendations import VALID_HORIZON_DAYS
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

CANDIDATE_MODEL_EVALUATION_VERSION = "CME-001"

VERDICT_VALIDATED = "VALIDATED"
VERDICT_REGRESSED = "REGRESSED"
VERDICT_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

REGRESSION_MARGIN = Decimal("0.10")


@dataclass(frozen=True)
class SegmentBucketMetric:
    dimension: str
    key: str
    evaluated_count: int
    success_count: int
    success_rate: Decimal | None


@dataclass(frozen=True)
class WindowEvaluation:
    version: str
    window: EvaluationWindow
    evaluated_count: int
    success_count: int
    failure_count: int
    success_rate: Decimal | None
    average_actual_return: Decimal | None
    average_predicted_return: Decimal | None
    mean_absolute_calibration_error: Decimal | None
    by_horizon: tuple[SegmentBucketMetric, ...]
    by_sector: tuple[SegmentBucketMetric, ...]
    by_market_cap_bucket: tuple[SegmentBucketMetric, ...]
    by_discovery_source: tuple[SegmentBucketMetric, ...]
    by_regime: tuple[SegmentBucketMetric, ...]
    insufficient_sample_dimensions: tuple[str, ...]


@dataclass(frozen=True)
class CandidateModelComparisonReport:
    version: str
    baseline: WindowEvaluation
    candidate: WindowEvaluation
    success_rate_delta: Decimal | None
    verdict: str


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _windows_overlap(a: EvaluationWindow, b: EvaluationWindow) -> bool:
    if a.end is not None and b.start is not None and a.end < b.start:
        return False
    if b.end is not None and a.start is not None and b.end < a.start:
        return False
    return True


def _evaluated_in_window(session: Session, window: EvaluationWindow) -> list[tuple[Prediction, PredictionOutcome]]:
    query = select(Prediction, PredictionOutcome).join(
        PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id
    ).where(PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    return list(session.execute(query).all())


def _segment_bucket(dimension: str, key: str, outcomes: list[PredictionOutcome]) -> SegmentBucketMetric:
    success_count = sum(1 for o in outcomes if o.outcome == "SUCCESS")
    return SegmentBucketMetric(
        dimension=dimension,
        key=key,
        evaluated_count=len(outcomes),
        success_count=success_count,
        success_rate=_rate(success_count, len(outcomes)),
    )


def _group_and_bucket(dimension: str, grouped: dict[str, list[PredictionOutcome]]) -> tuple[SegmentBucketMetric, ...]:
    return tuple(_segment_bucket(dimension, key, grouped[key]) for key in sorted(grouped))


def compute_window_evaluation(session: Session, window: EvaluationWindow) -> WindowEvaluation:
    """Every metric is computed only from `window`'s closed outcomes (no data
    outside its bounds is ever queried, mirroring M1.24/M1.25's point-in-time
    safety pattern -- AC: "evaluation data is strictly out-of-sample" when
    this is called with a disjoint window relative to another)."""
    evaluated = _evaluated_in_window(session, window)
    prediction_ids = [p.id for p, _ in evaluated]
    outcome_by_id = {p.id: o for p, o in evaluated}
    prediction_by_id = {p.id: p for p, _ in evaluated}

    success_count = sum(1 for _, o in evaluated if o.outcome == "SUCCESS")
    failure_count = sum(1 for _, o in evaluated if o.outcome == "FAILURE")
    success_rate = _rate(success_count, len(evaluated))

    average_actual_return = _mean([o.actual_return for _, o in evaluated])
    average_predicted_return = _mean([p.target_return for p, _ in evaluated])
    mean_absolute_calibration_error = _mean(
        [
            abs(p.predicted_probability - (Decimal("1") if o.outcome == "SUCCESS" else Decimal("0")))
            for p, o in evaluated
        ]
    )

    by_horizon_groups: dict[str, list[PredictionOutcome]] = {}
    for prediction, outcome in evaluated:
        by_horizon_groups.setdefault(str(prediction.horizon_days), []).append(outcome)
    # every supported horizon is always present, even with zero samples
    for horizon_days in VALID_HORIZON_DAYS:
        by_horizon_groups.setdefault(str(horizon_days), [])
    by_horizon = _group_and_bucket("horizon", by_horizon_groups)

    sector_rows = []
    source_rows = []
    regime_rows = []
    if prediction_ids:
        sector_rows = session.execute(
            select(RecommendationGeneration.prediction_id, DiscoverySegment.sector, DiscoverySegment.market_cap_bucket)
            .join(DiscoveryRecord, DiscoveryRecord.recommendation_generation_id == RecommendationGeneration.id)
            .join(DiscoverySegment, DiscoverySegment.discovery_record_id == DiscoveryRecord.id)
            .where(RecommendationGeneration.prediction_id.in_(prediction_ids))
        ).all()
        source_rows = session.execute(
            select(RecommendationGeneration.prediction_id, DiscoveryRecord.source)
            .join(DiscoveryRecord, DiscoveryRecord.recommendation_generation_id == RecommendationGeneration.id)
            .where(RecommendationGeneration.prediction_id.in_(prediction_ids))
        ).all()
        regime_rows = session.execute(
            select(RecommendationGeneration.prediction_id, MarketRegime.regime)
            .join(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
            .join(MarketRegime, MarketRegime.scan_id == ScanCandidate.scan_id)
            .where(RecommendationGeneration.prediction_id.in_(prediction_ids))
        ).all()

    by_sector_groups: dict[str, list[PredictionOutcome]] = {}
    by_market_cap_groups: dict[str, list[PredictionOutcome]] = {}
    for prediction_id, sector, market_cap_bucket in sector_rows:
        outcome = outcome_by_id[prediction_id]
        by_sector_groups.setdefault(sector, []).append(outcome)
        by_market_cap_groups.setdefault(market_cap_bucket, []).append(outcome)

    by_source_groups: dict[str, list[PredictionOutcome]] = {}
    for prediction_id, source in source_rows:
        by_source_groups.setdefault(source, []).append(outcome_by_id[prediction_id])

    by_regime_groups: dict[str, list[PredictionOutcome]] = {}
    for prediction_id, regime in regime_rows:
        by_regime_groups.setdefault(regime, []).append(outcome_by_id[prediction_id])

    by_sector = _group_and_bucket("sector", by_sector_groups)
    by_market_cap_bucket = _group_and_bucket("market_cap_bucket", by_market_cap_groups)
    by_discovery_source = _group_and_bucket("discovery_source", by_source_groups)
    by_regime = _group_and_bucket("regime", by_regime_groups)

    insufficient = []
    if len(evaluated) < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        insufficient.append("overall")
    for metric_group in (by_horizon, by_sector, by_market_cap_bucket, by_discovery_source, by_regime):
        for metric in metric_group:
            if metric.evaluated_count > 0 and metric.evaluated_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
                insufficient.append(f"{metric.dimension}:{metric.key}")

    return WindowEvaluation(
        version=CANDIDATE_MODEL_EVALUATION_VERSION,
        window=window,
        evaluated_count=len(evaluated),
        success_count=success_count,
        failure_count=failure_count,
        success_rate=success_rate,
        average_actual_return=average_actual_return,
        average_predicted_return=average_predicted_return,
        mean_absolute_calibration_error=mean_absolute_calibration_error,
        by_horizon=by_horizon,
        by_sector=by_sector,
        by_market_cap_bucket=by_market_cap_bucket,
        by_discovery_source=by_discovery_source,
        by_regime=by_regime,
        insufficient_sample_dimensions=tuple(insufficient),
    )


def compare_candidate_model(
    session: Session, *, baseline: EvaluationWindow, candidate: EvaluationWindow
) -> CandidateModelComparisonReport:
    """Evaluate baseline and candidate windows with the identical
    `compute_window_evaluation` call (AC: "candidate and baseline use
    identical evaluation inputs" -- literally the same function, same
    metrics, same segmentation). Raises `OverlappingEvaluationWindowsError`
    if the two windows overlap."""
    if _windows_overlap(baseline, candidate):
        raise OverlappingEvaluationWindowsError(
            f"baseline window '{baseline.label}' and candidate window '{candidate.label}' overlap"
        )

    baseline_eval = compute_window_evaluation(session, baseline)
    candidate_eval = compute_window_evaluation(session, candidate)

    if "overall" in baseline_eval.insufficient_sample_dimensions or "overall" in candidate_eval.insufficient_sample_dimensions:
        return CandidateModelComparisonReport(
            version=CANDIDATE_MODEL_EVALUATION_VERSION,
            baseline=baseline_eval,
            candidate=candidate_eval,
            success_rate_delta=None,
            verdict=VERDICT_INSUFFICIENT_EVIDENCE,
        )

    delta = candidate_eval.success_rate - baseline_eval.success_rate
    verdict = VERDICT_REGRESSED if delta <= -REGRESSION_MARGIN else VERDICT_VALIDATED

    return CandidateModelComparisonReport(
        version=CANDIDATE_MODEL_EVALUATION_VERSION,
        baseline=baseline_eval,
        candidate=candidate_eval,
        success_rate_delta=delta,
        verdict=verdict,
    )
