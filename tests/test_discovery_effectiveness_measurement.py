from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, SOURCE_WATCHLIST, record_discovery, route_discovery_through_pipeline
from app.discovery_effectiveness_measurement import (
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_NOT_REDUNDANT,
    VERDICT_OK,
    VERDICT_REDUNDANT,
    VERDICT_WEAK,
    compute_discovery_effectiveness_measurement,
    rank_discovery_sources,
)
from app.discovery_segmentation import record_segment_for_discovery
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.outcome_measurement import measure_outcome
from app.outcomes import evaluate_recommendation

AS_OF = datetime(2026, 3, 10, tzinfo=timezone.utc)
WINDOW = EvaluationWindow(
    label="w", start=datetime(2026, 3, 1, tzinfo=timezone.utc), end=datetime(2026, 3, 31, tzinfo=timezone.utc)
)
OUTSIDE_AS_OF = datetime(2026, 9, 1, tzinfo=timezone.utc)


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


def _make_scan(session, scan_date=date(2026, 3, 10)):
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_stock(session, symbol, sector="Energy", industry="Oil & Gas", market_cap=Decimal("30000")):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector=sector, industry=industry, market_cap=market_cap)
    session.add(stock)
    session.flush()
    return stock


def _discover_and_qualify(session, scan, stock, *, source, as_of=AS_OF, win=True, segment=True):
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
        atr_percent=Decimal("0.035"),  # horizon=1
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(
        session, scan_id=scan.id, stock_id=stock.id, source=source, rationale="test", discovered_at=as_of
    )
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    if segment:
        record_segment_for_discovery(session, discovery, stock, candidate)
    prediction = session.get(Prediction, generation.prediction_id)

    close = Decimal("106") if win else Decimal("95")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=as_of + timedelta(days=1),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    outcome = evaluate_recommendation(session, prediction)
    measure_outcome(session, outcome, measured_at=as_of)
    return discovery, prediction


def _reject_candidate(session, scan, stock, *, source, as_of=AS_OF):
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=Decimal("0.10"),  # fails consensus qualification
        confidence=Decimal("0.10"),
        sma20_distance=Decimal("-0.03"),
        volume_ratio_20d=Decimal("0.10"),
        atr_percent=Decimal("0.035"),
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(
        session, scan_id=scan.id, stock_id=stock.id, source=source, rationale="test", discovered_at=as_of
    )
    route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return discovery


def test_every_candidate_has_a_traceable_discovery_source(session):
    scan = _make_scan(session)
    stock = _make_stock(session, "AAA")
    _discover_and_qualify(session, scan, stock, source=SOURCE_CHATGPT)

    report = compute_discovery_effectiveness_measurement(session, WINDOW)

    assert report.by_source[0].source == SOURCE_CHATGPT
    assert report.by_source[0].discovered_count == 1


def test_funnel_distinguishes_rejection_from_qualification(session):
    scan = _make_scan(session)
    _reject_candidate(session, scan, _make_stock(session, "REJ"), source=SOURCE_CHATGPT)
    _discover_and_qualify(session, scan, _make_stock(session, "QUAL"), source=SOURCE_CHATGPT)

    report = compute_discovery_effectiveness_measurement(session, WINDOW)

    metric = report.by_source[0]
    assert metric.discovered_count == 2
    assert metric.routed_count == 2
    assert metric.rejected_count == 1
    assert metric.qualified_count == 1


def test_success_metrics_only_from_completed_outcomes(session):
    scan = _make_scan(session)
    stock = _make_stock(session, "OPEN1")
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    # no MarketPrice / evaluate_recommendation / measure_outcome -- still open

    report = compute_discovery_effectiveness_measurement(session, WINDOW)

    metric = report.by_source[0]
    assert metric.qualified_count == 1
    assert metric.evaluated_count == 0
    assert metric.success_rate is None


def test_small_sample_is_marked_insufficient(session):
    scan = _make_scan(session)
    _discover_and_qualify(session, scan, _make_stock(session, "AAA"), source=SOURCE_CHATGPT, win=True)

    report = compute_discovery_effectiveness_measurement(session, WINDOW)

    assert report.by_source[0].verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_weak_source_is_identified_against_a_strong_source(session):
    scan = _make_scan(session)
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        _discover_and_qualify(session, scan, _make_stock(session, f"S{i}"), source=SOURCE_CHATGPT, win=True)
    for i in range(total):
        _discover_and_qualify(session, scan, _make_stock(session, f"W{i}"), source=SOURCE_WATCHLIST, win=False)

    report = compute_discovery_effectiveness_measurement(session, WINDOW)

    by_source = {m.source: m for m in report.by_source}
    assert by_source[SOURCE_CHATGPT].verdict == VERDICT_OK
    assert by_source[SOURCE_WATCHLIST].verdict == VERDICT_WEAK
    assert rank_discovery_sources(report.by_source) == (SOURCE_CHATGPT, SOURCE_WATCHLIST)


def test_return_is_measured_by_source_and_segment(session):
    scan = _make_scan(session)
    _discover_and_qualify(session, scan, _make_stock(session, "AAA", sector="Energy"), source=SOURCE_CHATGPT, win=True)

    report = compute_discovery_effectiveness_measurement(session, WINDOW)

    assert report.by_source[0].average_realized_return is not None
    assert report.by_source[0].average_realized_return > 0
    sector_metric = next(m for m in report.by_sector if m.segment == "Energy")
    assert sector_metric.source == SOURCE_CHATGPT
    assert sector_metric.average_realized_return is not None


def test_segments_are_reported_only_where_available(session):
    scan = _make_scan(session)
    _discover_and_qualify(session, scan, _make_stock(session, "NOSEG"), source=SOURCE_CHATGPT, win=True, segment=False)

    report = compute_discovery_effectiveness_measurement(session, WINDOW)

    assert report.by_sector == ()
    assert report.by_industry == ()
    assert report.by_market_cap_bucket == ()


def test_redundant_sources_are_identified_by_co_discovery(session):
    scan = _make_scan(session)
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        stock = _make_stock(session, f"OVERLAP{i}")
        candidate = ScanCandidate(
            scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
            predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
            volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
            model_version="test-model-1", feature_version="FV-001",
        )
        session.add(candidate)
        session.flush()
        record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
        record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_WATCHLIST, rationale="t", discovered_at=AS_OF)

    report = compute_discovery_effectiveness_measurement(session, WINDOW)

    redundancy = {m.source: m for m in report.redundancy}
    assert redundancy[SOURCE_CHATGPT].verdict == VERDICT_REDUNDANT
    assert redundancy[SOURCE_CHATGPT].redundancy_rate == Decimal("1")


def test_non_overlapping_sources_are_not_redundant(session):
    scan = _make_scan(session)
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        _discover_and_qualify(session, scan, _make_stock(session, f"UNIQ{i}"), source=SOURCE_CHATGPT, win=True)

    report = compute_discovery_effectiveness_measurement(session, WINDOW)

    redundancy = {m.source: m for m in report.redundancy}
    assert redundancy[SOURCE_CHATGPT].verdict == VERDICT_NOT_REDUNDANT
    assert redundancy[SOURCE_CHATGPT].redundancy_rate == Decimal("0")


def test_common_period_window_excludes_discoveries_outside_it(session):
    scan_in = _make_scan(session, scan_date=date(2026, 3, 10))
    scan_out = _make_scan(session, scan_date=date(2026, 9, 1))
    _discover_and_qualify(session, scan_in, _make_stock(session, "IN"), source=SOURCE_CHATGPT, as_of=AS_OF, win=True)
    _discover_and_qualify(session, scan_out, _make_stock(session, "OUT"), source=SOURCE_CHATGPT, as_of=OUTSIDE_AS_OF, win=True)

    report = compute_discovery_effectiveness_measurement(session, WINDOW)

    assert report.by_source[0].discovered_count == 1
