"""EPIC-M1.129: determine whether a recommendation's realized return
reflects genuine stock-specific opportunity, not just a rising broad
market or sector carrying it along.

**Benchmark price data is genuinely new to this platform** -- unlike
M1.109's sector-relative work (which reused same-scan
`ScanCandidate.sma20_distance`, already-collected data), no index price
series existed before this EPIC. `Benchmark`/`BenchmarkDailyPrice` are
new, minimal tables; prices are ingested through the same
`market_data.yahoo.YahooFinanceClient` this platform already uses for
equities -- its `fetch_daily_candles` is symbol-generic, so an index
ticker like `^NSEI` flows through unchanged, not a new vendor
integration (see `ingest_benchmark_daily_history`).

**Industry-level benchmarking is honestly out of scope for this first
version** -- this platform has no curated industry-index mapping, only
`Stock.sector`, and only for the fixed set of sectors named in
`SECTOR_BENCHMARK_SYMBOLS`. This is the same posture M1.109 already took
for peer valuation/fundamentals: named here rather than fabricated. An
unmapped sector, or missing benchmark price data on the relevant dates,
yields `INSUFFICIENT_BENCHMARK_DATA` rather than a guessed number.

**Point-in-time correctness**: benchmark prices are looked up strictly
at-or-before the relevant date (entry date, evaluation date) -- never a
later, unavailable price.

**Raw stock return and relative performance stay separate metrics**
(acceptance criteria): `PredictionOutcome.actual_return` (M1.5) is read
verbatim as the stock's own realized return, never recomputed here;
`benchmark_return_pct`/`relative_alpha` are additional, separate columns.

**"Evaluate target/SL outcomes relative to benchmark behavior over the
same horizon"** (scope) is satisfied by comparing `outcome.actual_return`
-- the very value that already determined `target_hit`/`stop_hit` -- to
the benchmark's return over the identical `entry_date`->`evaluation_date`
window; a finer-grained, day-by-day trace of exactly when the target/stop
triggered relative to the benchmark is out of scope, since
`PredictionOutcome` itself doesn't record an intra-horizon timestamp.

Propose-only: no write path to `Prediction`, `PositiveOpportunityRanking`,
`PredictionUsefulnessAssessment`, or any ranking/Trust Score table --
"feed relative opportunity into ranking and usefulness measurement"
(scope) remains a future revision's job, the same posture M1.109/M1.122/
M1.130 already established.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Benchmark,
    BenchmarkDailyPrice,
    BenchmarkPerformanceReport,
    BenchmarkRelativeAssessment,
    Prediction,
    PredictionOutcome,
    Stock,
)
from .out_of_sample_validation import EvaluationWindow
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK, WEAKNESS_MARGIN

BENCHMARK_RELATIVE_VERSION = "BRA-001"

LEVEL_BROAD_MARKET = "BROAD_MARKET"
LEVEL_SECTOR = "SECTOR"

BROAD_MARKET_CODE = "BROAD_MARKET"
BROAD_MARKET_SYMBOL = "^NSEI"
BROAD_MARKET_LABEL = "Nifty 50"

# Fixed, documented, versioned mapping -- not learned or fitted. A sector
# not listed here has no benchmark and is honestly reported as
# INSUFFICIENT_BENCHMARK_DATA rather than guessed.
SECTOR_BENCHMARK_SYMBOLS: dict[str, tuple[str, str]] = {
    "IT": ("^CNXIT", "Nifty IT"),
    "TECHNOLOGY": ("^CNXIT", "Nifty IT"),
    "BANKING": ("^NSEBANK", "Nifty Bank"),
    "FINANCIAL SERVICES": ("^NSEBANK", "Nifty Bank"),
    "PHARMA": ("^CNXPHARMA", "Nifty Pharma"),
    "PHARMACEUTICALS": ("^CNXPHARMA", "Nifty Pharma"),
    "AUTO": ("^CNXAUTO", "Nifty Auto"),
    "AUTOMOBILE": ("^CNXAUTO", "Nifty Auto"),
    "FMCG": ("^CNXFMCG", "Nifty FMCG"),
    "METAL": ("^CNXMETAL", "Nifty Metal"),
    "METALS": ("^CNXMETAL", "Nifty Metal"),
    "ENERGY": ("^CNXENERGY", "Nifty Energy"),
    "REALTY": ("^CNXREALTY", "Nifty Realty"),
    "REAL ESTATE": ("^CNXREALTY", "Nifty Realty"),
}

VERDICT_GENUINE_RELATIVE_OPPORTUNITY = "GENUINE_RELATIVE_OPPORTUNITY"
VERDICT_MARKET_DRIVEN = "MARKET_DRIVEN"
VERDICT_UNDERPERFORMED_BENCHMARK = "UNDERPERFORMED_BENCHMARK"
VERDICT_INSUFFICIENT_BENCHMARK_DATA = "INSUFFICIENT_BENCHMARK_DATA"

# Fixed, documented, versioned policy constant -- not learned or fitted.
ALPHA_GENUINE_THRESHOLD = Decimal("0.01")


def get_or_create_benchmark(
    session: Session, *, code: str, level: str, label: str, symbol: str, sector: str | None = None,
) -> Benchmark:
    existing = session.scalar(select(Benchmark).where(Benchmark.code == code))
    if existing is not None:
        return existing
    benchmark = Benchmark(code=code, level=level, label=label, symbol=symbol, sector=sector, is_active=True)
    session.add(benchmark)
    session.commit()
    session.refresh(benchmark)
    return benchmark


def _sector_benchmark(session: Session, sector: str | None) -> Benchmark | None:
    if sector is None:
        return None
    mapping = SECTOR_BENCHMARK_SYMBOLS.get(sector.strip().upper())
    if mapping is None:
        return None
    symbol, label = mapping
    code = f"SECTOR_{sector.strip().upper().replace(' ', '_')}"
    return get_or_create_benchmark(session, code=code, level=LEVEL_SECTOR, label=label, symbol=symbol, sector=sector)


def _price_at_or_before(session: Session, benchmark_id: int, on_or_before: date) -> Decimal | None:
    return session.scalar(
        select(BenchmarkDailyPrice.close)
        .where(BenchmarkDailyPrice.benchmark_id == benchmark_id, BenchmarkDailyPrice.trade_date <= on_or_before)
        .order_by(BenchmarkDailyPrice.trade_date.desc())
        .limit(1)
    )


def _benchmark_return(session: Session, benchmark: Benchmark, *, entry_date: date, evaluation_date: date) -> Decimal | None:
    start_price = _price_at_or_before(session, benchmark.id, entry_date)
    end_price = _price_at_or_before(session, benchmark.id, evaluation_date)
    if start_price is None or end_price is None or start_price == 0:
        return None
    return (end_price - start_price) / start_price


def _classify(stock_return: Decimal, benchmark_return: Decimal | None) -> tuple[Decimal | None, str]:
    if benchmark_return is None:
        return None, VERDICT_INSUFFICIENT_BENCHMARK_DATA
    alpha = stock_return - benchmark_return
    if alpha >= ALPHA_GENUINE_THRESHOLD:
        return alpha, VERDICT_GENUINE_RELATIVE_OPPORTUNITY
    if alpha <= -ALPHA_GENUINE_THRESHOLD:
        return alpha, VERDICT_UNDERPERFORMED_BENCHMARK
    return alpha, VERDICT_MARKET_DRIVEN


def assess_benchmark_relative_opportunity(
    session: Session, prediction: Prediction, *, evaluated_at: datetime,
) -> tuple[BenchmarkRelativeAssessment, ...]:
    """One row per benchmark level with a mapped benchmark (broad market
    always; sector only if `Stock.sector` is in `SECTOR_BENCHMARK_SYMBOLS`).
    Idempotent by `(prediction_id, benchmark_level, evaluated_at)`. Returns
    an empty tuple if the prediction has no outcome yet -- there is no
    horizon return to compare."""
    outcome = session.scalar(select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction.id))
    if outcome is None:
        return ()
    stock = session.get(Stock, prediction.stock_id)
    entry_date = prediction.as_of_timestamp.date()
    evaluation_date = outcome.evaluation_date.date()

    broad_market = get_or_create_benchmark(
        session, code=BROAD_MARKET_CODE, level=LEVEL_BROAD_MARKET, label=BROAD_MARKET_LABEL, symbol=BROAD_MARKET_SYMBOL,
    )
    candidates = [broad_market]
    sector_benchmark = _sector_benchmark(session, stock.sector if stock else None)
    if sector_benchmark is not None:
        candidates.append(sector_benchmark)

    assessments = []
    for benchmark in candidates:
        existing = session.scalar(
            select(BenchmarkRelativeAssessment).where(
                BenchmarkRelativeAssessment.prediction_id == prediction.id,
                BenchmarkRelativeAssessment.benchmark_level == benchmark.level,
                BenchmarkRelativeAssessment.evaluated_at == evaluated_at,
            )
        )
        if existing is not None:
            assessments.append(existing)
            continue

        benchmark_return = _benchmark_return(session, benchmark, entry_date=entry_date, evaluation_date=evaluation_date)
        alpha, verdict = _classify(outcome.actual_return, benchmark_return)

        assessment = BenchmarkRelativeAssessment(
            prediction_id=prediction.id, benchmark_level=benchmark.level, benchmark_id=benchmark.id,
            benchmark_code=benchmark.code, stock_return_pct=outcome.actual_return, benchmark_return_pct=benchmark_return,
            relative_alpha=alpha, verdict=verdict, evaluated_at=evaluated_at, assessment_rule_version=BENCHMARK_RELATIVE_VERSION,
        )
        session.add(assessment)
        session.commit()
        session.refresh(assessment)
        assessments.append(assessment)
    return tuple(assessments)


def get_benchmark_relative_history(session: Session, prediction_id: int) -> tuple[BenchmarkRelativeAssessment, ...]:
    return tuple(
        session.scalars(
            select(BenchmarkRelativeAssessment)
            .where(BenchmarkRelativeAssessment.prediction_id == prediction_id)
            .order_by(BenchmarkRelativeAssessment.id.asc())
        ).all()
    )


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _outcomes_in_window_by_environment(
    session: Session, window: EvaluationWindow, *, environment: str | None, benchmark_level: str,
) -> list[str]:
    query = (
        select(PredictionOutcome.outcome)
        .select_from(PredictionOutcome)
        .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
        .where(PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    )
    if environment is not None:
        query = query.join(
            BenchmarkRelativeAssessment,
            (BenchmarkRelativeAssessment.prediction_id == Prediction.id)
            & (BenchmarkRelativeAssessment.benchmark_level == benchmark_level),
        ).where(BenchmarkRelativeAssessment.verdict == environment)
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    return list(session.scalars(query).all())


def compare_benchmark_relative_performance(
    session: Session, *, environment: str, window: EvaluationWindow, computed_at: datetime, benchmark_level: str = LEVEL_BROAD_MARKET,
) -> BenchmarkPerformanceReport:
    """Segment prediction quality by benchmark-relative environment
    (scope) -- always computes and persists a fresh, independent report
    row, the same "report" posture as M1.85/M1.99/M1.102/M1.108/M1.109."""
    segment_outcomes = _outcomes_in_window_by_environment(session, window, environment=environment, benchmark_level=benchmark_level)
    baseline_outcomes = _outcomes_in_window_by_environment(session, window, environment=None, benchmark_level=benchmark_level)

    segment_sample_count = len(segment_outcomes)
    baseline_sample_count = len(baseline_outcomes)
    segment_success_rate = _rate(sum(1 for o in segment_outcomes if o == "SUCCESS"), segment_sample_count)
    baseline_success_rate = _rate(sum(1 for o in baseline_outcomes if o == "SUCCESS"), baseline_sample_count)

    if (
        segment_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or baseline_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or segment_success_rate is None
        or baseline_success_rate is None
    ):
        verdict = VERDICT_INSUFFICIENT_SAMPLE
    elif baseline_success_rate - segment_success_rate >= WEAKNESS_MARGIN:
        verdict = VERDICT_WEAK
    else:
        verdict = VERDICT_OK

    report = BenchmarkPerformanceReport(
        benchmark_relative_environment=environment, benchmark_level=benchmark_level, window_label=window.label,
        segment_sample_count=segment_sample_count, segment_success_rate=segment_success_rate,
        baseline_sample_count=baseline_sample_count, baseline_success_rate=baseline_success_rate,
        verdict=verdict, computed_at=computed_at, report_rule_version=BENCHMARK_RELATIVE_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_benchmark_performance_history(session: Session, environment: str) -> tuple[BenchmarkPerformanceReport, ...]:
    return tuple(
        session.scalars(
            select(BenchmarkPerformanceReport)
            .where(BenchmarkPerformanceReport.benchmark_relative_environment == environment)
            .order_by(BenchmarkPerformanceReport.id.asc())
        ).all()
    )


def ingest_benchmark_daily_history(session: Session, client, benchmark: Benchmark, from_date: date, to_date: date) -> int:
    """Fetch and idempotently persist daily closing prices for one
    benchmark, reusing this platform's existing `fetch_daily_candles`
    provider contract (`market_data.yahoo.YahooFinanceClient` already
    implements it for equities; an index ticker like `^NSEI` flows
    through the same call unchanged -- no new vendor integration)."""
    candles = client.fetch_daily_candles(benchmark.symbol, from_date, to_date)
    inserted = 0
    for candle in candles:
        if len(candle) < 6:
            continue
        trade_date = datetime.fromisoformat(candle[0]).date()
        close = Decimal(str(candle[4]))
        if close <= 0:
            continue
        existing = session.scalar(
            select(BenchmarkDailyPrice).where(
                BenchmarkDailyPrice.benchmark_id == benchmark.id, BenchmarkDailyPrice.trade_date == trade_date,
            )
        )
        if existing is not None:
            continue
        session.add(
            BenchmarkDailyPrice(
                benchmark_id=benchmark.id, trade_date=trade_date, close=close, source=getattr(client, "source", "yahoo-finance"),
            )
        )
        inserted += 1
    session.commit()
    return inserted
