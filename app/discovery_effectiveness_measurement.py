"""EPIC-M1.42: measure whether each discovery source and segment actually
produces useful positive recommendations and successful outcomes, over a
common comparison period so two sources are never compared unfairly across
different lifetimes.

Composes rather than duplicates M1.28's discovery funnel (its public
`VERDICT_OK`/`VERDICT_WEAK`/`VERDICT_INSUFFICIENT_SAMPLE` vocabulary is reused
here unchanged), M1.16's `MIN_SAMPLE_SIZE_FOR_COMPARISON`/`WEAKNESS_MARGIN`
evidence-gating constants, M1.25's `EvaluationWindow` for the common-period
bound, M1.34's already-persisted `DiscoverySegment` (sector/market_cap_bucket/
industry, "where available") rather than reclassifying from `Stock`, and
M1.38's `OutcomeMeasurement` (outcome classification + realized return) for
"discovery-to-success metrics are calculated only from completed outcomes."

Adds two capabilities M1.28 did not cover: return magnitude (not just a
success/failure count) segmented by source and by sector/market-cap-bucket/
industry/regime, and a structural redundancy measure -- since `DiscoveryRecord`
has a `(scan_id, stock_id, source)` uniqueness constraint, the same stock
discovered by more than one source on the same scan is detectable directly
from that constraint's own shape, with no new table required.

Read-only and deterministic; writes nothing anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .discovery_effectiveness import VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK
from .models import (
    DiscoveryRecord,
    DiscoverySegment,
    MarketRegime,
    OutcomeMeasurement,
    Prediction,
    PredictionOutcome,
    RecommendationGeneration,
)
from .out_of_sample_validation import EvaluationWindow
from .outcome_measurement import OUTCOME_SUCCESS, OUTCOME_FAILURE
from .recommendation_generator import OUTCOME_NOT_QUALIFIED, OUTCOME_QUALIFIED
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

DISCOVERY_EFFECTIVENESS_MEASUREMENT_VERSION = "DEM-001"

REDUNDANCY_THRESHOLD = Decimal("0.50")
VERDICT_REDUNDANT = "REDUNDANT"
VERDICT_NOT_REDUNDANT = "NOT_REDUNDANT"


@dataclass(frozen=True)
class SourceEffectivenessMetric:
    source: str
    discovered_count: int
    routed_count: int
    rejected_count: int
    qualified_count: int
    evaluated_count: int
    success_count: int
    failure_count: int
    success_rate: Decimal | None
    average_realized_return: Decimal | None
    verdict: str


@dataclass(frozen=True)
class SourceSegmentMetric:
    source: str
    segment: str
    evaluated_count: int
    success_count: int
    success_rate: Decimal | None
    average_realized_return: Decimal | None


@dataclass(frozen=True)
class SourceRedundancyMetric:
    source: str
    discovered_count: int
    co_discovered_count: int
    redundancy_rate: Decimal | None
    verdict: str


@dataclass(frozen=True)
class DiscoveryEffectivenessMeasurementReport:
    version: str
    window: EvaluationWindow
    by_source: tuple[SourceEffectivenessMetric, ...]
    by_sector: tuple[SourceSegmentMetric, ...]
    by_market_cap_bucket: tuple[SourceSegmentMetric, ...]
    by_industry: tuple[SourceSegmentMetric, ...]
    by_regime: tuple[SourceSegmentMetric, ...]
    redundancy: tuple[SourceRedundancyMetric, ...]
    ranking: tuple[str, ...]


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _mean(values: list) -> Decimal | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _success_verdict(sample_count: int, success_rate: Decimal | None, overall_success_rate: Decimal | None) -> str:
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or success_rate is None or overall_success_rate is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if overall_success_rate - success_rate >= WEAKNESS_MARGIN:
        return VERDICT_WEAK
    return VERDICT_OK


def _redundancy_verdict(sample_count: int, redundancy_rate: Decimal | None) -> str:
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or redundancy_rate is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if redundancy_rate >= REDUNDANCY_THRESHOLD:
        return VERDICT_REDUNDANT
    return VERDICT_NOT_REDUNDANT


def _segment_metrics(seg: dict) -> tuple[SourceSegmentMetric, ...]:
    result = []
    for (source, segment_value), measurements in sorted(seg.items()):
        evaluated_count = len(measurements)
        success_count = sum(1 for m in measurements if m.outcome_classification == OUTCOME_SUCCESS)
        result.append(
            SourceSegmentMetric(
                source=source,
                segment=segment_value,
                evaluated_count=evaluated_count,
                success_count=success_count,
                success_rate=_rate(success_count, evaluated_count),
                average_realized_return=_mean([m.realized_return for m in measurements]),
            )
        )
    return tuple(result)


def rank_discovery_sources(by_source: tuple) -> tuple[str, ...]:
    """A fixed, deterministic ranking rule -- descending success rate, ties
    broken alphabetically -- never a fitted or optimized one. A source
    without sufficient evidence is left out of the ranking entirely rather
    than placed arbitrarily (AC: "discovery sources can be ranked
    objectively")."""
    eligible = [m for m in by_source if m.verdict != VERDICT_INSUFFICIENT_SAMPLE and m.success_rate is not None]
    ranked = sorted(eligible, key=lambda m: (-m.success_rate, m.source))
    return tuple(m.source for m in ranked)


def compute_discovery_effectiveness_measurement(
    session: Session, window: EvaluationWindow
) -> DiscoveryEffectivenessMeasurementReport:
    """Every candidate has a traceable discovery source by construction
    (scope: "track candidates by discovery source"). Filters on
    `DiscoveryRecord.discovered_at` -- the one timestamp every candidate has
    regardless of whether it was ever routed or qualified -- so two sources
    are compared over the exact same period even if one started discovering
    stocks later than the other (scope: "compare discovery channels over
    common periods")."""
    query = (
        select(DiscoveryRecord, RecommendationGeneration, Prediction, PredictionOutcome, OutcomeMeasurement, DiscoverySegment, MarketRegime)
        .outerjoin(RecommendationGeneration, RecommendationGeneration.id == DiscoveryRecord.recommendation_generation_id)
        .outerjoin(Prediction, Prediction.id == RecommendationGeneration.prediction_id)
        .outerjoin(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .outerjoin(OutcomeMeasurement, OutcomeMeasurement.prediction_outcome_id == PredictionOutcome.id)
        .outerjoin(DiscoverySegment, DiscoverySegment.discovery_record_id == DiscoveryRecord.id)
        .outerjoin(MarketRegime, MarketRegime.scan_id == DiscoveryRecord.scan_id)
    )
    if window.start is not None:
        query = query.where(DiscoveryRecord.discovered_at >= window.start)
    if window.end is not None:
        query = query.where(DiscoveryRecord.discovered_at <= window.end)
    rows = session.execute(query).all()

    by_source_raw: dict[str, dict] = {}
    source_pairs: dict[str, list[tuple]] = {}
    pair_sources: dict[tuple, set] = {}
    seg_sector: dict[tuple, list] = {}
    seg_cap: dict[tuple, list] = {}
    seg_industry: dict[tuple, list] = {}
    seg_regime: dict[tuple, list] = {}

    for discovery, generation, _prediction, _outcome, measurement, segment, regime in rows:
        source = discovery.source
        bucket = by_source_raw.setdefault(
            source, dict(discovered=0, routed=0, rejected=0, qualified=0, success=0, failure=0, returns=[])
        )
        bucket["discovered"] += 1
        pair = (discovery.scan_id, discovery.stock_id)
        source_pairs.setdefault(source, []).append(pair)
        pair_sources.setdefault(pair, set()).add(source)

        if generation is None:
            continue
        bucket["routed"] += 1
        if generation.outcome == OUTCOME_NOT_QUALIFIED:
            bucket["rejected"] += 1
            continue
        if generation.outcome != OUTCOME_QUALIFIED:
            continue
        bucket["qualified"] += 1

        if measurement is None:
            continue  # not yet measured -- excluded (AC: completed outcomes only)

        if measurement.realized_return is not None:
            bucket["returns"].append(measurement.realized_return)

        if measurement.outcome_classification == OUTCOME_SUCCESS:
            bucket["success"] += 1
        elif measurement.outcome_classification == OUTCOME_FAILURE:
            bucket["failure"] += 1
        else:
            continue  # NEUTRAL / INSUFFICIENT_DATA -- non-directional

        if segment is not None:
            seg_sector.setdefault((source, segment.sector), []).append(measurement)
            seg_cap.setdefault((source, segment.market_cap_bucket), []).append(measurement)
            seg_industry.setdefault((source, segment.industry), []).append(measurement)
        if regime is not None:
            seg_regime.setdefault((source, regime.regime), []).append(measurement)

    total_success = sum(b["success"] for b in by_source_raw.values())
    total_evaluated = sum(b["success"] + b["failure"] for b in by_source_raw.values())
    overall_success_rate = _rate(total_success, total_evaluated)

    by_source = []
    for source in sorted(by_source_raw):
        b = by_source_raw[source]
        evaluated_count = b["success"] + b["failure"]
        success_rate = _rate(b["success"], evaluated_count)
        by_source.append(
            SourceEffectivenessMetric(
                source=source,
                discovered_count=b["discovered"],
                routed_count=b["routed"],
                rejected_count=b["rejected"],
                qualified_count=b["qualified"],
                evaluated_count=evaluated_count,
                success_count=b["success"],
                failure_count=b["failure"],
                success_rate=success_rate,
                average_realized_return=_mean(b["returns"]),
                verdict=_success_verdict(evaluated_count, success_rate, overall_success_rate),
            )
        )
    by_source = tuple(by_source)

    redundancy = []
    for source in sorted(by_source_raw):
        pairs = source_pairs.get(source, [])
        co_discovered = sum(1 for pair in pairs if len(pair_sources[pair]) > 1)
        redundancy_rate = _rate(co_discovered, len(pairs))
        redundancy.append(
            SourceRedundancyMetric(
                source=source,
                discovered_count=len(pairs),
                co_discovered_count=co_discovered,
                redundancy_rate=redundancy_rate,
                verdict=_redundancy_verdict(len(pairs), redundancy_rate),
            )
        )

    return DiscoveryEffectivenessMeasurementReport(
        version=DISCOVERY_EFFECTIVENESS_MEASUREMENT_VERSION,
        window=window,
        by_source=by_source,
        by_sector=_segment_metrics(seg_sector),
        by_market_cap_bucket=_segment_metrics(seg_cap),
        by_industry=_segment_metrics(seg_industry),
        by_regime=_segment_metrics(seg_regime),
        redundancy=tuple(redundancy),
        ranking=rank_discovery_sources(by_source),
    )
