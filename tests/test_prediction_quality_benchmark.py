from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.outcomes import evaluate_recommendation
from app.prediction_quality_benchmark import (
    BENCHMARK_AVAILABLE,
    BENCHMARK_DATA_UNAVAILABLE,
    BENCHMARK_NOT_REQUESTED,
    QUALITY_BENCHMARK_VERSION,
    SEGMENT_HORIZON,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_MEASURED,
    compute_prediction_quality_benchmark,
    get_benchmark_report_history,
)
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 2, 1, tzinfo=timezone.utc)
WINDOW = EvaluationWindow(label="full-history", start=None, end=None)
_scan_counter = iter(range(100000))


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


def _make_scan(session):
    scan_date = date(2027, 2, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_evaluated(session, symbol, *, win: bool, sector=None, market_cap=None):
    scan = _make_scan(session)
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector=sector, market_cap=market_cap)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    assert prediction.horizon_days == 1

    close = Decimal("106") if win else Decimal("95")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    evaluate_recommendation(session, prediction)
    return prediction


def _seed(session, *, total, win_count, prefix, sector=None, market_cap=None):
    for i in range(total):
        _make_evaluated(session, f"{prefix}{i}", win=(i < win_count), sector=sector, market_cap=market_cap)


def _make_benchmark_stock(session, symbol="NIFTY50", *, entry_close, exit_close):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF, open=entry_close, high=entry_close, low=entry_close, close=entry_close,
        volume=1000, source="test",
    ))
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1), open=exit_close, high=exit_close, low=exit_close,
        close=exit_close, volume=1000, source="test",
    ))
    session.commit()
    return stock


def test_insufficient_sample(session):
    _seed(session, total=5, win_count=5, prefix="A")

    report = compute_prediction_quality_benchmark(
        session, model_version=MODEL_VERSION, window=WINDOW, benchmark_stock_id=None, computed_at=AS_OF,
    )

    assert report.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert report.directional_accuracy is None
    assert report.benchmark_verdict == BENCHMARK_NOT_REQUESTED
    assert report.benchmark_rule_version == QUALITY_BENCHMARK_VERSION


def test_core_metrics_are_measured_correctly(session):
    total, win_count = 24, 18
    _seed(session, total=total, win_count=win_count, prefix="B")

    report = compute_prediction_quality_benchmark(
        session, model_version=MODEL_VERSION, window=WINDOW, benchmark_stock_id=None, computed_at=AS_OF,
    )

    assert report.verdict == VERDICT_MEASURED
    assert report.sample_count == total
    assert report.directional_accuracy == Decimal("0.75")
    assert report.target_hit_rate == Decimal("0.75")
    assert report.stop_hit_rate == Decimal("0.25")
    assert report.avg_expected_return == Decimal("0.05")
    assert report.avg_realized_return == Decimal("0.03")
    assert report.avg_max_favorable_excursion == Decimal("0.0425")
    assert report.avg_max_adverse_excursion == Decimal("0.0225")
    assert report.avg_time_to_exit_days == Decimal("1")
    assert report.benchmark_verdict == BENCHMARK_NOT_REQUESTED


def test_benchmark_comparison_with_real_coverage(session):
    total, win_count = 24, 18
    _seed(session, total=total, win_count=win_count, prefix="C")
    benchmark = _make_benchmark_stock(session, entry_close=Decimal("100"), exit_close=Decimal("102"))

    report = compute_prediction_quality_benchmark(
        session, model_version=MODEL_VERSION, window=WINDOW, benchmark_stock_id=benchmark.id, computed_at=AS_OF,
    )

    assert report.benchmark_verdict == BENCHMARK_AVAILABLE
    assert report.benchmark_coverage_count == total
    assert report.avg_benchmark_return == Decimal("0.02")
    assert report.avg_excess_return == Decimal("0.01")
    assert report.trust_reduction_recommended is False


def test_underperforming_benchmark_recommends_trust_reduction(session):
    total, win_count = 24, 18
    _seed(session, total=total, win_count=win_count, prefix="D")
    benchmark = _make_benchmark_stock(session, entry_close=Decimal("100"), exit_close=Decimal("110"))

    report = compute_prediction_quality_benchmark(
        session, model_version=MODEL_VERSION, window=WINDOW, benchmark_stock_id=benchmark.id, computed_at=AS_OF,
    )

    assert report.avg_benchmark_return == Decimal("0.10")
    assert report.avg_excess_return == Decimal("0.03") - Decimal("0.10")
    assert report.trust_reduction_recommended is True


def test_benchmark_unavailable_when_no_price_coverage(session):
    total, win_count = 24, 18
    _seed(session, total=total, win_count=win_count, prefix="E")
    empty_benchmark = Stock(symbol="EMPTY", exchange="NSE", is_active=True)
    session.add(empty_benchmark)
    session.commit()

    report = compute_prediction_quality_benchmark(
        session, model_version=MODEL_VERSION, window=WINDOW, benchmark_stock_id=empty_benchmark.id, computed_at=AS_OF,
    )

    assert report.benchmark_verdict == BENCHMARK_DATA_UNAVAILABLE
    assert report.avg_benchmark_return is None
    assert report.trust_reduction_recommended is False


def test_segment_breakdown_includes_only_sufficient_segments(session):
    total, win_count = MIN_SAMPLE_SIZE_FOR_COMPARISON, MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed(session, total=total, win_count=win_count, prefix="F", sector="Energy")

    report = compute_prediction_quality_benchmark(
        session, model_version=MODEL_VERSION, window=WINDOW, benchmark_stock_id=None, computed_at=AS_OF,
    )

    horizon_entries = [s for s in report.segment_breakdown if s["dimension"] == SEGMENT_HORIZON]
    assert len(horizon_entries) == 1
    assert horizon_entries[0]["key"] == "1"
    assert horizon_entries[0]["sample_count"] == total
    assert horizon_entries[0]["success_rate"] == "1"


def test_report_history_is_retained(session):
    _seed(session, total=5, win_count=5, prefix="G")

    compute_prediction_quality_benchmark(session, model_version=MODEL_VERSION, window=WINDOW, benchmark_stock_id=None, computed_at=AS_OF)
    compute_prediction_quality_benchmark(session, model_version=MODEL_VERSION, window=WINDOW, benchmark_stock_id=None, computed_at=AS_OF + timedelta(days=1))

    assert len(get_benchmark_report_history(session, MODEL_VERSION)) == 2


def test_never_writes_to_predictions(session):
    total, win_count = 24, 18
    _seed(session, total=total, win_count=win_count, prefix="H")
    before = {p.id: p.opportunity_score for p in session.query(Prediction).all()}

    compute_prediction_quality_benchmark(session, model_version=MODEL_VERSION, window=WINDOW, benchmark_stock_id=None, computed_at=AS_OF)

    after = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    assert before == after
