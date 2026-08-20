"""EPIC-M1.27: measure recommendation performance across sector, industry,
market-cap, and liquidity segments, further split by horizon -- read-only,
deterministic, versioned, and never rewriting a historical classification or
score.

Reuses M1.34's `DiscoverySegment` wholesale as the "stable classification
persisted at recommendation time" scope item 1 already calls for -- that
table is already an immutable, discovery-time snapshot (see its own
completion report), so this EPIC adds no new classification logic, only the
performance aggregation on top of it.

`DiscoverySegment` coverage is not universal: only candidates that were
explicitly segmented (via `record_segments_for_scan`) have one. This module
does not attempt to force universal coverage -- that would mean modifying
`app/continuous_discovery.py`'s already-merged orchestration, out of scope
here -- so segments with zero or few samples are reported with an explicit
`INSUFFICIENT_SAMPLE` verdict, honestly reflecting current coverage rather
than fabricating conclusions from a partial population.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DiscoveryRecord, DiscoverySegment, Prediction, PredictionOutcome, RecommendationGeneration
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

SEGMENT_PERFORMANCE_VERSION = "SPL-001"

VERDICT_OK = "OK"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

DIMENSION_MARKET_CAP_BUCKET = "market_cap_bucket"
DIMENSION_SECTOR = "sector"
DIMENSION_INDUSTRY = "industry"
DIMENSION_LIQUIDITY_BUCKET = "liquidity_bucket"

_DIMENSIONS = (
    DIMENSION_MARKET_CAP_BUCKET,
    DIMENSION_SECTOR,
    DIMENSION_INDUSTRY,
    DIMENSION_LIQUIDITY_BUCKET,
)


@dataclass(frozen=True)
class SegmentMetric:
    dimension: str
    key: str
    horizon_days: int
    evaluated_count: int
    success_count: int
    success_rate: Decimal | None
    average_actual_return: Decimal | None
    verdict: str


@dataclass(frozen=True)
class SegmentPerformanceReport:
    report_version: str
    evaluated_count: int
    metrics: tuple[SegmentMetric, ...]


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def compute_segment_performance_report(session: Session) -> SegmentPerformanceReport:
    """Every statistic is a plain deterministic aggregate over stored
    `Prediction`/`PredictionOutcome`/`DiscoverySegment` rows (scope item 5,
    "machine-readable metrics"); only already-evaluated (`SUCCESS`/`FAILURE`)
    outcomes are considered, so no future/open information ever enters a
    segment's metric (AC: "no future information leaks into segment
    attribution")."""
    rows = session.execute(
        select(Prediction, PredictionOutcome).join(
            PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id
        ).where(PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    ).all()
    if not rows:
        return SegmentPerformanceReport(report_version=SEGMENT_PERFORMANCE_VERSION, evaluated_count=0, metrics=())

    prediction_ids = [p.id for p, _ in rows]
    outcome_by_prediction_id = {p.id: o for p, o in rows}
    horizon_by_prediction_id = {p.id: p.horizon_days for p, _ in rows}

    segment_rows = session.execute(
        select(RecommendationGeneration.prediction_id, DiscoverySegment)
        .join(DiscoveryRecord, DiscoveryRecord.recommendation_generation_id == RecommendationGeneration.id)
        .join(DiscoverySegment, DiscoverySegment.discovery_record_id == DiscoveryRecord.id)
        .where(RecommendationGeneration.prediction_id.in_(prediction_ids))
    ).all()

    # (dimension, key, horizon_days) -> list[PredictionOutcome]
    buckets: dict[tuple[str, str, int], list[PredictionOutcome]] = {}
    seen_segment_values: dict[int, set[tuple[str, str]]] = {}
    for prediction_id, segment in segment_rows:
        horizon_days = horizon_by_prediction_id[prediction_id]
        outcome = outcome_by_prediction_id[prediction_id]
        values = {
            DIMENSION_MARKET_CAP_BUCKET: segment.market_cap_bucket,
            DIMENSION_SECTOR: segment.sector,
            DIMENSION_INDUSTRY: segment.industry,
            DIMENSION_LIQUIDITY_BUCKET: segment.liquidity_bucket,
        }
        already_counted = seen_segment_values.setdefault(prediction_id, set())
        for dimension, key in values.items():
            dedup_key = (dimension, key)
            if dedup_key in already_counted:
                continue
            already_counted.add(dedup_key)
            buckets.setdefault((dimension, key, horizon_days), []).append(outcome)

    metrics = []
    for (dimension, key, horizon_days), outcomes in sorted(buckets.items()):
        success_count = sum(1 for o in outcomes if o.outcome == "SUCCESS")
        verdict = VERDICT_INSUFFICIENT_SAMPLE if len(outcomes) < MIN_SAMPLE_SIZE_FOR_COMPARISON else VERDICT_OK
        metrics.append(
            SegmentMetric(
                dimension=dimension,
                key=key,
                horizon_days=horizon_days,
                evaluated_count=len(outcomes),
                success_count=success_count,
                success_rate=Decimal(success_count) / Decimal(len(outcomes)) if outcomes else None,
                average_actual_return=_mean([o.actual_return for o in outcomes]),
                verdict=verdict,
            )
        )

    return SegmentPerformanceReport(
        report_version=SEGMENT_PERFORMANCE_VERSION,
        evaluated_count=len(rows),
        metrics=tuple(metrics),
    )
