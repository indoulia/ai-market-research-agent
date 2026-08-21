from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.benchmark_relative_alpha import (
    BENCHMARK_RELATIVE_VERSION,
    BROAD_MARKET_CODE,
    LEVEL_BROAD_MARKET,
    LEVEL_SECTOR,
    VERDICT_GENUINE_RELATIVE_OPPORTUNITY,
    VERDICT_INSUFFICIENT_BENCHMARK_DATA,
    VERDICT_MARKET_DRIVEN,
    VERDICT_UNDERPERFORMED_BENCHMARK,
    assess_benchmark_relative_opportunity,
    compare_benchmark_relative_performance,
    get_benchmark_relative_history,
    get_or_create_benchmark,
    ingest_benchmark_daily_history,
)
from app.db import Base
from app.models import Benchmark, BenchmarkDailyPrice, Prediction, PredictionOutcome, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.trust_report import VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
EVAL_AT = datetime(2027, 1, 8, tzinfo=timezone.utc)
_counter = iter(range(1000000))


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _make_prediction_with_outcome(session, *, sector, actual_return, outcome="SUCCESS", as_of=AS_OF, evaluation_date=EVAL_AT):
    n = next(_counter)
    stock = Stock(symbol=f"S{n}", exchange="NSE", sector=sector, is_active=True)
    session.add(stock)
    session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=as_of, entry_price=Decimal("100"), horizon_days=7,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.flush()
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=evaluation_date, highest_price=Decimal("110"), lowest_price=Decimal("99"),
        closing_price=Decimal("105"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.01"),
        actual_return=actual_return, prediction_error=Decimal("0.01"), target_hit=(outcome == "SUCCESS"),
        stop_hit=(outcome == "FAILURE"), outcome=outcome,
    ))
    session.commit()
    return prediction


def _seed_broad_market_prices(session, *, start_close, end_close, start_date=AS_OF.date(), end_date=EVAL_AT.date()):
    benchmark = get_or_create_benchmark(
        session, code=BROAD_MARKET_CODE, level=LEVEL_BROAD_MARKET, label="Nifty 50", symbol="^NSEI",
    )
    session.add(BenchmarkDailyPrice(benchmark_id=benchmark.id, trade_date=start_date, close=start_close, source="test"))
    session.add(BenchmarkDailyPrice(benchmark_id=benchmark.id, trade_date=end_date, close=end_close, source="test"))
    session.commit()
    return benchmark


def test_insufficient_benchmark_data_when_no_prices(session):
    prediction = _make_prediction_with_outcome(session, sector="TECH", actual_return=Decimal("0.05"))

    assessments = assess_benchmark_relative_opportunity(session, prediction, evaluated_at=EVAL_AT)

    broad_market = [a for a in assessments if a.benchmark_level == LEVEL_BROAD_MARKET][0]
    assert broad_market.verdict == VERDICT_INSUFFICIENT_BENCHMARK_DATA
    assert broad_market.benchmark_return_pct is None
    assert broad_market.stock_return_pct == Decimal("0.05")
    assert broad_market.assessment_rule_version == BENCHMARK_RELATIVE_VERSION


def test_genuine_relative_opportunity_when_stock_beats_benchmark(session):
    _seed_broad_market_prices(session, start_close=Decimal("100"), end_close=Decimal("101"))  # +1% benchmark
    prediction = _make_prediction_with_outcome(session, sector="TECH", actual_return=Decimal("0.08"))  # +8% stock

    assessments = assess_benchmark_relative_opportunity(session, prediction, evaluated_at=EVAL_AT)

    broad_market = [a for a in assessments if a.benchmark_level == LEVEL_BROAD_MARKET][0]
    assert broad_market.verdict == VERDICT_GENUINE_RELATIVE_OPPORTUNITY
    assert broad_market.relative_alpha == Decimal("0.07")


def test_market_driven_when_stock_tracks_benchmark(session):
    _seed_broad_market_prices(session, start_close=Decimal("100"), end_close=Decimal("105"))  # +5% benchmark
    prediction = _make_prediction_with_outcome(session, sector="TECH", actual_return=Decimal("0.052"))  # +5.2% stock

    assessments = assess_benchmark_relative_opportunity(session, prediction, evaluated_at=EVAL_AT)

    broad_market = [a for a in assessments if a.benchmark_level == LEVEL_BROAD_MARKET][0]
    assert broad_market.verdict == VERDICT_MARKET_DRIVEN


def test_underperformed_benchmark_when_stock_lags(session):
    _seed_broad_market_prices(session, start_close=Decimal("100"), end_close=Decimal("110"))  # +10% benchmark
    prediction = _make_prediction_with_outcome(session, sector="TECH", actual_return=Decimal("0.02"))  # +2% stock

    assessments = assess_benchmark_relative_opportunity(session, prediction, evaluated_at=EVAL_AT)

    broad_market = [a for a in assessments if a.benchmark_level == LEVEL_BROAD_MARKET][0]
    assert broad_market.verdict == VERDICT_UNDERPERFORMED_BENCHMARK
    assert broad_market.relative_alpha == Decimal("-0.08")


def test_sector_level_assessment_only_for_mapped_sectors(session):
    prediction_mapped = _make_prediction_with_outcome(session, sector="IT", actual_return=Decimal("0.05"))
    prediction_unmapped = _make_prediction_with_outcome(session, sector="UNCLASSIFIED_SECTOR_XYZ", actual_return=Decimal("0.05"))

    mapped_assessments = assess_benchmark_relative_opportunity(session, prediction_mapped, evaluated_at=EVAL_AT)
    unmapped_assessments = assess_benchmark_relative_opportunity(session, prediction_unmapped, evaluated_at=EVAL_AT)

    assert {a.benchmark_level for a in mapped_assessments} == {LEVEL_BROAD_MARKET, LEVEL_SECTOR}
    assert {a.benchmark_level for a in unmapped_assessments} == {LEVEL_BROAD_MARKET}


def test_no_outcome_yet_returns_no_assessments(session):
    n = next(_counter)
    stock = Stock(symbol=f"S{n}", exchange="NSE", sector="TECH", is_active=True)
    session.add(stock)
    session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=7,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.commit()

    assert assess_benchmark_relative_opportunity(session, prediction, evaluated_at=EVAL_AT) == ()


def test_idempotent(session):
    _seed_broad_market_prices(session, start_close=Decimal("100"), end_close=Decimal("101"))
    prediction = _make_prediction_with_outcome(session, sector="TECH", actual_return=Decimal("0.08"))

    first = assess_benchmark_relative_opportunity(session, prediction, evaluated_at=EVAL_AT)
    second = assess_benchmark_relative_opportunity(session, prediction, evaluated_at=EVAL_AT)

    assert [a.id for a in first] == [a.id for a in second]
    assert len(get_benchmark_relative_history(session, prediction.id)) == len(first)


def test_point_in_time_price_lookup_uses_nearest_prior_trade_date(session):
    # No price exactly on AS_OF/EVAL_AT dates -- only an earlier trading day for each.
    benchmark = get_or_create_benchmark(session, code=BROAD_MARKET_CODE, level=LEVEL_BROAD_MARKET, label="Nifty 50", symbol="^NSEI")
    session.add(BenchmarkDailyPrice(benchmark_id=benchmark.id, trade_date=AS_OF.date() - timedelta(days=1), close=Decimal("100"), source="test"))
    session.add(BenchmarkDailyPrice(benchmark_id=benchmark.id, trade_date=EVAL_AT.date() - timedelta(days=1), close=Decimal("102"), source="test"))
    session.commit()
    prediction = _make_prediction_with_outcome(session, sector="TECH", actual_return=Decimal("0.08"))

    assessments = assess_benchmark_relative_opportunity(session, prediction, evaluated_at=EVAL_AT)

    broad_market = [a for a in assessments if a.benchmark_level == LEVEL_BROAD_MARKET][0]
    assert broad_market.benchmark_return_pct == Decimal("0.02")


def test_compare_benchmark_relative_performance_insufficient_sample(session):
    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=EVAL_AT + timedelta(days=1))

    report = compare_benchmark_relative_performance(
        session, environment=VERDICT_GENUINE_RELATIVE_OPPORTUNITY, window=window, computed_at=EVAL_AT,
    )

    assert report.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_compare_benchmark_relative_performance_ok_when_in_line(session):
    _seed_broad_market_prices(session, start_close=Decimal("100"), end_close=Decimal("101"))
    for _ in range(20):
        prediction = _make_prediction_with_outcome(session, sector="TECH", actual_return=Decimal("0.08"), outcome="SUCCESS")
        assess_benchmark_relative_opportunity(session, prediction, evaluated_at=EVAL_AT)
    for _ in range(20):
        _make_prediction_with_outcome(session, sector="TECH", actual_return=Decimal("-0.02"), outcome="FAILURE")

    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=EVAL_AT + timedelta(days=1))
    report = compare_benchmark_relative_performance(
        session, environment=VERDICT_GENUINE_RELATIVE_OPPORTUNITY, window=window, computed_at=EVAL_AT,
    )

    assert report.verdict == VERDICT_OK
    assert report.segment_sample_count == 20
    assert report.segment_success_rate == Decimal("1")


def test_ingest_benchmark_daily_history_is_idempotent(session):
    benchmark = get_or_create_benchmark(session, code=BROAD_MARKET_CODE, level=LEVEL_BROAD_MARKET, label="Nifty 50", symbol="^NSEI")

    class FakeClient:
        source = "yahoo-finance"

        def fetch_daily_candles(self, symbol, from_date, to_date):
            assert symbol == "^NSEI"
            return [
                ["2027-01-01T00:00:00+00:00", 100.0, 101.0, 99.0, 100.5, 0],
                ["2027-01-02T00:00:00+00:00", 100.5, 102.0, 100.0, 101.5, 0],
            ]

    client = FakeClient()
    first = ingest_benchmark_daily_history(session, client, benchmark, AS_OF.date(), EVAL_AT.date())
    second = ingest_benchmark_daily_history(session, client, benchmark, AS_OF.date(), EVAL_AT.date())

    assert first == 2
    assert second == 0
