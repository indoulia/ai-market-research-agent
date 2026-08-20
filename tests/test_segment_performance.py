from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.discovery_segmentation import record_segment_for_discovery
from app.models import DailyCandidateScan, DiscoveryRecord, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcomes import evaluate_recommendation
from app.segment_performance import (
    DIMENSION_SECTOR,
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    SEGMENT_PERFORMANCE_VERSION,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_OK,
    compute_segment_performance_report,
)

AS_OF = datetime(2026, 8, 21, tzinfo=timezone.utc)


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
    scan = DailyCandidateScan(scan_date=date(2026, 8, 21), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


# M1.10's fixed thresholds: atr_percent selects the horizon, it is not a
# direct parameter of the generator.
_ATR_PERCENT_FOR_HORIZON = {1: Decimal("0.035"), 3: Decimal("0.020"), 5: Decimal("0.010"), 7: Decimal("0.001")}


def _make_evaluated_and_segmented(session, scan, symbol, *, sector, market_cap, win: bool, horizon_days=1):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector=sector, market_cap=market_cap)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
        atr_percent=_ATR_PERCENT_FOR_HORIZON[horizon_days],
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()

    discovery = record_discovery(
        session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="test", discovered_at=AS_OF
    )
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    record_segment_for_discovery(session, discovery, stock, candidate)
    prediction = session.get(Prediction, generation.prediction_id)

    filler = [100] * (horizon_days - 1)
    closes = filler + ([106] if win else [95])
    for offset, close in enumerate(closes, start=1):
        close = Decimal(str(close))
        session.add(MarketPrice(
            stock_id=stock.id, timestamp=AS_OF + timedelta(days=offset),
            open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
            volume=1000, source="test",
        ))
    session.flush()
    evaluate_recommendation(session, prediction)
    return prediction


def test_empty_history_reports_no_metrics(session):
    report = compute_segment_performance_report(session)

    assert report.report_version == SEGMENT_PERFORMANCE_VERSION
    assert report.evaluated_count == 0
    assert report.metrics == ()


def test_sector_metric_below_minimum_sample_is_insufficient(session):
    scan = _make_scan(session)
    for i in range(5):
        _make_evaluated_and_segmented(session, scan, f"S{i}", sector="Energy", market_cap=Decimal("30000"), win=False)

    report = compute_segment_performance_report(session)
    energy_metric = next(m for m in report.metrics if m.dimension == DIMENSION_SECTOR and m.key == "Energy")

    assert energy_metric.evaluated_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert energy_metric.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_sector_metric_with_enough_samples_reports_success_rate_and_return(session):
    scan = _make_scan(session)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated_and_segmented(
            session, scan, f"S{i}", sector="Technology", market_cap=Decimal("2000"), win=(i % 2 == 0)
        )

    report = compute_segment_performance_report(session)
    tech_metric = next(m for m in report.metrics if m.dimension == DIMENSION_SECTOR and m.key == "Technology")

    assert tech_metric.evaluated_count == MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert tech_metric.verdict == VERDICT_OK
    assert tech_metric.success_rate == Decimal("0.5")
    assert tech_metric.average_actual_return is not None


def test_metrics_are_segmented_by_horizon_independently(session):
    scan = _make_scan(session)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated_and_segmented(
            session, scan, f"H1_{i}", sector="Energy", market_cap=Decimal("30000"), win=True, horizon_days=1
        )
    for i in range(5):
        _make_evaluated_and_segmented(
            session, scan, f"H3_{i}", sector="Energy", market_cap=Decimal("30000"), win=False, horizon_days=3
        )

    report = compute_segment_performance_report(session)
    horizon_1_metric = next(
        m for m in report.metrics if m.dimension == DIMENSION_SECTOR and m.key == "Energy" and m.horizon_days == 1
    )
    horizon_3_metric = next(
        m for m in report.metrics if m.dimension == DIMENSION_SECTOR and m.key == "Energy" and m.horizon_days == 3
    )

    assert horizon_1_metric.success_rate == Decimal("1")
    assert horizon_1_metric.verdict == VERDICT_OK
    assert horizon_3_metric.evaluated_count == 5
    assert horizon_3_metric.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_reclassifying_stock_sector_does_not_rewrite_historical_metrics(session):
    scan = _make_scan(session)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated_and_segmented(session, scan, f"S{i}", sector="Energy", market_cap=Decimal("30000"), win=True)

    first_report = compute_segment_performance_report(session)

    # reclassify one stock's sector after the fact -- the historical
    # DiscoverySegment snapshot must not be affected
    stock = session.scalar(select(Stock).where(Stock.symbol == "S0"))
    stock.sector = "Technology"
    session.flush()

    second_report = compute_segment_performance_report(session)

    energy_first = next(m for m in first_report.metrics if m.dimension == DIMENSION_SECTOR and m.key == "Energy")
    energy_second = next(m for m in second_report.metrics if m.dimension == DIMENSION_SECTOR and m.key == "Energy")
    assert energy_first.evaluated_count == energy_second.evaluated_count == MIN_SAMPLE_SIZE_FOR_COMPARISON
