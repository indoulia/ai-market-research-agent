"""EPIC-M1.82: measure whether positive recommendations create useful
investment outcomes relative to appropriate market and sector
benchmarks -- not merely directional accuracy.

Every core metric here is already computed and immutably stored by
earlier EPICs -- this module composes and aggregates, it never
recomputes: directional accuracy/target-hit/stop-hit/realized return
(M1.5's `PredictionOutcome`), expected return (M1.13's `Prediction.
target_return`), maximum favorable/adverse excursion (M1.5's
`maximum_return`/`maximum_drawdown`), horizon (`Prediction.horizon_days`),
regime (M1.26's `classify_market_regime`), sector (`Stock.sector`),
market-cap bucket (M1.34's `classify_market_cap_bucket`), and discovery
source (M1.17's `DiscoveryRecord.source`). "Time-to-exit" is the one
genuinely new derived value: `evaluation_date - as_of_timestamp`.

**Benchmark comparison is real, not hardcoded to NIFTY.** This platform
has no dedicated market-index ingestion pipeline, so rather than
fabricating one, `benchmark_stock_id` accepts *any* already-ingested
`Stock` (an index-tracking ETF, a sector proxy, or -- once a future
EPIC ingests one via M1.3's existing, generic `YahooFinanceClient`/
`ingest_daily_history` -- a NIFTY-tracking instrument itself). For each
evaluated prediction, the benchmark's own return over the *exact same
holding period* (`as_of_timestamp` to `evaluation_date`) is computed
from that stock's own `MarketPrice` rows when they cover both endpoints;
a prediction whose holding period the benchmark doesn't cover is simply
excluded from the benchmark average, never fabricated (AC: "benchmark-
relative performance is reproducible" holds because this is a pure,
deterministic aggregate over already-immutable data).

"Feed benchmark-relative performance into Trust and learning" (scope)
is a forward-compatible capability: `trust_reduction_recommended` is
exposed for a future consumer (M1.84) -- this module has no write path
to `Prediction`, `ScanCandidate`, or `PredictionTrustScore` itself.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .discovery_segmentation import classify_market_cap_bucket
from .market_regime import classify_market_regime
from .models import (
    DiscoveryRecord,
    MarketPrice,
    Prediction,
    PredictionOutcome,
    PredictionQualityBenchmarkReport,
    RecommendationGeneration,
    ScanCandidate,
    Stock,
)
from .out_of_sample_validation import EvaluationWindow
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

QUALITY_BENCHMARK_VERSION = "PQB-001"

VERDICT_MEASURED = "MEASURED"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

BENCHMARK_AVAILABLE = "BENCHMARK_AVAILABLE"
BENCHMARK_DATA_UNAVAILABLE = "BENCHMARK_DATA_UNAVAILABLE"
BENCHMARK_NOT_REQUESTED = "BENCHMARK_NOT_REQUESTED"

SEGMENT_HORIZON = "HORIZON"
SEGMENT_REGIME = "REGIME"
SEGMENT_SECTOR = "SECTOR"
SEGMENT_MARKET_CAP = "MARKET_CAP"
SEGMENT_DISCOVERY_SOURCE = "DISCOVERY_SOURCE"


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _mean(values: list[Decimal]) -> Decimal | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values) / Decimal(len(values))


def _evaluated_rows(
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


def _benchmark_return(session: Session, benchmark_stock_id: int, entry_at: datetime, exit_at: datetime) -> Decimal | None:
    entry_price = session.scalar(
        select(MarketPrice.close)
        .where(MarketPrice.stock_id == benchmark_stock_id, MarketPrice.timestamp <= entry_at)
        .order_by(MarketPrice.timestamp.desc())
    )
    exit_price = session.scalar(
        select(MarketPrice.close)
        .where(MarketPrice.stock_id == benchmark_stock_id, MarketPrice.timestamp <= exit_at)
        .order_by(MarketPrice.timestamp.desc())
    )
    if entry_price is None or exit_price is None or entry_price == 0:
        return None
    return (exit_price - entry_price) / entry_price


def _regime_for_prediction(session: Session, prediction: Prediction) -> str | None:
    scan_id = session.execute(
        select(ScanCandidate.scan_id)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalar_one_or_none()
    if scan_id is None:
        return None
    return classify_market_regime(session, scan_id).regime


def _discovery_source_for_prediction(session: Session, prediction: Prediction) -> str | None:
    return session.execute(
        select(DiscoveryRecord.source)
        .join(RecommendationGeneration, RecommendationGeneration.id == DiscoveryRecord.recommendation_generation_id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalar_one_or_none()


def _segment_breakdown(session: Session, rows: list[tuple[Prediction, PredictionOutcome]]) -> list[dict]:
    """Segments results by horizon, regime, sector, market-cap, and
    discovery source "when evidence permits" (scope) -- a segment below
    `MIN_SAMPLE_SIZE_FOR_COMPARISON` is simply omitted, never used to
    draw an unsafe conclusion."""
    stocks_by_id = {
        stock.id: stock
        for stock in session.scalars(select(Stock).where(Stock.id.in_({p.stock_id for p, _ in rows}))).all()
    }

    dimensions = {
        SEGMENT_HORIZON: lambda p: str(p.horizon_days),
        SEGMENT_REGIME: lambda p: _regime_for_prediction(session, p),
        SEGMENT_SECTOR: lambda p: stocks_by_id[p.stock_id].sector,
        SEGMENT_MARKET_CAP: lambda p: classify_market_cap_bucket(stocks_by_id[p.stock_id].market_cap),
        SEGMENT_DISCOVERY_SOURCE: lambda p: _discovery_source_for_prediction(session, p),
    }

    breakdown = []
    for dimension, key_fn in dimensions.items():
        grouped: dict[str, list[PredictionOutcome]] = {}
        for prediction, outcome in rows:
            key = key_fn(prediction)
            if key is None:
                continue
            grouped.setdefault(key, []).append(outcome)
        for key in sorted(grouped):
            outcomes = grouped[key]
            if len(outcomes) < MIN_SAMPLE_SIZE_FOR_COMPARISON:
                continue
            success_count = sum(1 for o in outcomes if o.outcome == "SUCCESS")
            breakdown.append({
                "dimension": dimension,
                "key": key,
                "sample_count": len(outcomes),
                "success_rate": str(_rate(success_count, len(outcomes))),
            })
    return breakdown


def compute_prediction_quality_benchmark(
    session: Session,
    *,
    model_version: str,
    window: EvaluationWindow,
    benchmark_stock_id: int | None,
    computed_at: datetime,
) -> PredictionQualityBenchmarkReport:
    """Deterministic, reproducible aggregate over already-immutable
    M1.5/M1.13 data (AC: "benchmark-relative performance is
    reproducible"). Below `MIN_SAMPLE_SIZE_FOR_COMPARISON`, the verdict
    is explicitly `VERDICT_INSUFFICIENT_SAMPLE` and every metric stays
    `None` (AC: "metrics include sample counts and uncertainty")."""
    rows = _evaluated_rows(session, model_version, window)
    sample_count = len(rows)

    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        report = PredictionQualityBenchmarkReport(
            model_version=model_version, window_label=window.label, sample_count=sample_count,
            directional_accuracy=None, target_hit_rate=None, stop_hit_rate=None, avg_expected_return=None,
            avg_realized_return=None, avg_max_favorable_excursion=None, avg_max_adverse_excursion=None,
            avg_time_to_exit_days=None, benchmark_stock_id=benchmark_stock_id, avg_benchmark_return=None,
            avg_excess_return=None, benchmark_coverage_count=0,
            benchmark_verdict=BENCHMARK_NOT_REQUESTED if benchmark_stock_id is None else BENCHMARK_DATA_UNAVAILABLE,
            segment_breakdown=[], verdict=VERDICT_INSUFFICIENT_SAMPLE, trust_reduction_recommended=False,
            computed_at=computed_at, benchmark_rule_version=QUALITY_BENCHMARK_VERSION,
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        return report

    success_count = sum(1 for _, o in rows if o.outcome == "SUCCESS")
    directional_accuracy = _rate(success_count, sample_count)
    target_hit_rate = _rate(sum(1 for _, o in rows if o.target_hit), sample_count)
    stop_hit_rate = _rate(sum(1 for _, o in rows if o.stop_hit), sample_count)
    avg_expected_return = _mean([p.target_return for p, _ in rows])
    avg_realized_return = _mean([o.actual_return for _, o in rows])
    avg_max_favorable_excursion = _mean([o.maximum_return for _, o in rows])
    avg_max_adverse_excursion = _mean([o.maximum_drawdown for _, o in rows])
    avg_time_to_exit_days = _mean([
        Decimal((o.evaluation_date.replace(tzinfo=None) - p.as_of_timestamp.replace(tzinfo=None)).days)
        for p, o in rows
    ])

    benchmark_returns: list[Decimal] = []
    if benchmark_stock_id is not None:
        for prediction, outcome in rows:
            benchmark_return = _benchmark_return(session, benchmark_stock_id, prediction.as_of_timestamp, outcome.evaluation_date)
            if benchmark_return is not None:
                benchmark_returns.append(benchmark_return)

    benchmark_coverage_count = len(benchmark_returns)
    if benchmark_stock_id is None:
        benchmark_verdict = BENCHMARK_NOT_REQUESTED
        avg_benchmark_return = None
        avg_excess_return = None
    elif benchmark_coverage_count == 0:
        benchmark_verdict = BENCHMARK_DATA_UNAVAILABLE
        avg_benchmark_return = None
        avg_excess_return = None
    else:
        benchmark_verdict = BENCHMARK_AVAILABLE
        avg_benchmark_return = _mean(benchmark_returns)
        avg_excess_return = avg_realized_return - avg_benchmark_return

    trust_reduction_recommended = avg_excess_return is not None and avg_excess_return < Decimal("0")

    report = PredictionQualityBenchmarkReport(
        model_version=model_version,
        window_label=window.label,
        sample_count=sample_count,
        directional_accuracy=directional_accuracy,
        target_hit_rate=target_hit_rate,
        stop_hit_rate=stop_hit_rate,
        avg_expected_return=avg_expected_return,
        avg_realized_return=avg_realized_return,
        avg_max_favorable_excursion=avg_max_favorable_excursion,
        avg_max_adverse_excursion=avg_max_adverse_excursion,
        avg_time_to_exit_days=avg_time_to_exit_days,
        benchmark_stock_id=benchmark_stock_id,
        avg_benchmark_return=avg_benchmark_return,
        avg_excess_return=avg_excess_return,
        benchmark_coverage_count=benchmark_coverage_count,
        benchmark_verdict=benchmark_verdict,
        segment_breakdown=_segment_breakdown(session, rows),
        verdict=VERDICT_MEASURED,
        trust_reduction_recommended=trust_reduction_recommended,
        computed_at=computed_at,
        benchmark_rule_version=QUALITY_BENCHMARK_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_benchmark_report_history(session: Session, model_version: str) -> tuple[PredictionQualityBenchmarkReport, ...]:
    return tuple(
        session.scalars(
            select(PredictionQualityBenchmarkReport)
            .where(PredictionQualityBenchmarkReport.model_version == model_version)
            .order_by(PredictionQualityBenchmarkReport.id.asc())
        ).all()
    )
