"""EPIC-M1.28: measure which discovery sources actually produce successful
recommendations, tracking the full candidate -> recommendation -> outcome
funnel per source -- discovered, routed, rejected (M1.8 consensus failure),
qualified, and (once closed) evaluated/success/failure/unevaluable -- so
"candidate rejection" and "recommendation failure" are never conflated into
one number.

Read-only, deterministic, versioned; the only write this EPIC makes anywhere
is the immutability guard added to `app/discovery.py`'s `DiscoveryRecord`
(the AC "historical provenance cannot be overwritten" required closing a
real, pre-existing gap -- that table had no guard at all before this EPIC),
which does not change any of M1.17/M1.19/M1.33's existing behavior.

Horizon segmentation is fully covered (every qualified `Prediction` has one).
Market-regime segmentation (`app.market_regime`, M1.26) is reported only
"where available" (scope item 3's own qualifier): a `MarketRegime` row exists
only for scans that were explicitly classified, so a discovery whose scan was
never classified simply doesn't contribute to that breakdown, rather than
being force-fit into a fabricated regime.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    DiscoveryRecord,
    MarketRegime,
    Prediction,
    PredictionOutcome,
    RecommendationGeneration,
    ScanCandidate,
)
from .recommendation_generator import OUTCOME_NOT_QUALIFIED, OUTCOME_QUALIFIED
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

DISCOVERY_EFFECTIVENESS_VERSION = "DEL-001"

VERDICT_OK = "OK"
VERDICT_WEAK = "WEAK"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


@dataclass(frozen=True)
class DiscoverySourceFunnel:
    source: str
    discovered_count: int
    routed_count: int
    rejected_count: int
    qualified_count: int
    evaluated_count: int
    success_count: int
    failure_count: int
    unevaluable_count: int
    open_count: int
    success_rate: Decimal | None
    verdict: str


@dataclass(frozen=True)
class SourceHorizonMetric:
    source: str
    horizon_days: int
    evaluated_count: int
    success_count: int
    success_rate: Decimal | None


@dataclass(frozen=True)
class SourceRegimeMetric:
    source: str
    regime: str
    evaluated_count: int
    success_count: int
    success_rate: Decimal | None


@dataclass(frozen=True)
class DiscoveryEffectivenessReport:
    report_version: str
    by_source: tuple[DiscoverySourceFunnel, ...]
    by_source_and_horizon: tuple[SourceHorizonMetric, ...]
    by_source_and_regime: tuple[SourceRegimeMetric, ...]


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _verdict(sample_count: int, success_rate: Decimal | None, overall_success_rate: Decimal | None) -> str:
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or success_rate is None or overall_success_rate is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if overall_success_rate - success_rate >= WEAKNESS_MARGIN:
        return VERDICT_WEAK
    return VERDICT_OK


def compute_discovery_effectiveness_report(session: Session) -> DiscoveryEffectivenessReport:
    """Every candidate's discovery provenance is traceable by construction
    (`DiscoveryRecord` exists for every row this query starts from -- scope
    item 1); discovery effectiveness only becomes measurable once an outcome
    actually closes (scope item 2: open/unevaluated recommendations are
    counted but excluded from `success_rate`)."""
    rows = session.execute(
        select(DiscoveryRecord, RecommendationGeneration, Prediction, PredictionOutcome, MarketRegime)
        .outerjoin(RecommendationGeneration, RecommendationGeneration.id == DiscoveryRecord.recommendation_generation_id)
        .outerjoin(Prediction, Prediction.id == RecommendationGeneration.prediction_id)
        .outerjoin(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .outerjoin(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
        .outerjoin(MarketRegime, MarketRegime.scan_id == DiscoveryRecord.scan_id)
    ).all()

    # Global evaluated-success rate across all sources, for the weak/ok verdict.
    all_evaluated_outcomes = [outcome for _, _, _, outcome, _ in rows if outcome is not None and outcome.outcome in ("SUCCESS", "FAILURE")]
    overall_success_rate = _rate(
        sum(1 for o in all_evaluated_outcomes if o.outcome == "SUCCESS"), len(all_evaluated_outcomes)
    )

    by_source_raw: dict[str, dict] = {}
    by_source_horizon: dict[tuple[str, int], list[PredictionOutcome]] = {}
    by_source_regime: dict[tuple[str, str], list[PredictionOutcome]] = {}

    for discovery, generation, prediction, outcome, regime in rows:
        bucket = by_source_raw.setdefault(
            discovery.source,
            dict(discovered=0, routed=0, rejected=0, qualified=0, success=0, failure=0, unevaluable=0, open=0),
        )
        bucket["discovered"] += 1
        if generation is None:
            continue
        bucket["routed"] += 1
        if generation.outcome == OUTCOME_NOT_QUALIFIED:
            bucket["rejected"] += 1
            continue
        if generation.outcome != OUTCOME_QUALIFIED:
            continue
        bucket["qualified"] += 1

        if outcome is None:
            bucket["open"] += 1
            continue
        if outcome.outcome == "UNEVALUABLE":
            bucket["unevaluable"] += 1
            continue
        if outcome.outcome == "SUCCESS":
            bucket["success"] += 1
        elif outcome.outcome == "FAILURE":
            bucket["failure"] += 1
        else:
            continue

        by_source_horizon.setdefault((discovery.source, prediction.horizon_days), []).append(outcome)
        if regime is not None:
            by_source_regime.setdefault((discovery.source, regime.regime), []).append(outcome)

    by_source = []
    for source in sorted(by_source_raw):
        b = by_source_raw[source]
        evaluated_count = b["success"] + b["failure"]
        success_rate = _rate(b["success"], evaluated_count)
        by_source.append(
            DiscoverySourceFunnel(
                source=source,
                discovered_count=b["discovered"],
                routed_count=b["routed"],
                rejected_count=b["rejected"],
                qualified_count=b["qualified"],
                evaluated_count=evaluated_count,
                success_count=b["success"],
                failure_count=b["failure"],
                unevaluable_count=b["unevaluable"],
                open_count=b["open"],
                success_rate=success_rate,
                verdict=_verdict(evaluated_count, success_rate, overall_success_rate),
            )
        )

    by_source_and_horizon = tuple(
        SourceHorizonMetric(
            source=source,
            horizon_days=horizon_days,
            evaluated_count=len(outcomes),
            success_count=sum(1 for o in outcomes if o.outcome == "SUCCESS"),
            success_rate=_rate(sum(1 for o in outcomes if o.outcome == "SUCCESS"), len(outcomes)),
        )
        for (source, horizon_days), outcomes in sorted(by_source_horizon.items())
    )

    by_source_and_regime = tuple(
        SourceRegimeMetric(
            source=source,
            regime=regime,
            evaluated_count=len(outcomes),
            success_count=sum(1 for o in outcomes if o.outcome == "SUCCESS"),
            success_rate=_rate(sum(1 for o in outcomes if o.outcome == "SUCCESS"), len(outcomes)),
        )
        for (source, regime), outcomes in sorted(by_source_regime.items())
    )

    return DiscoveryEffectivenessReport(
        report_version=DISCOVERY_EFFECTIVENESS_VERSION,
        by_source=tuple(by_source),
        by_source_and_horizon=by_source_and_horizon,
        by_source_and_regime=by_source_and_regime,
    )
