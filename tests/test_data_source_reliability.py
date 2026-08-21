from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_source_reliability import (
    COVERAGE_TRUST_THRESHOLD,
    DATA_SOURCE_RELIABILITY_VERSION,
    RELIABILITY_SUCCESS_THRESHOLD,
    compute_data_source_reliability_report,
)
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.discovery_effectiveness import VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK
from app.evidence_snapshot import capture_evidence_snapshot
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.refresh_policy import DATA_TYPE_MARKET, record_fetch_attempt
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

AS_OF = datetime(2026, 12, 10, tzinfo=timezone.utc)
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


def test_empty_platform_reports_insufficient_sample_everywhere(session):
    report = compute_data_source_reliability_report(session)

    assert report.version == DATA_SOURCE_RELIABILITY_VERSION
    market = next(m for m in report.by_data_type if m.data_type == DATA_TYPE_MARKET)
    assert market.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert report.by_evidence_category == ()


def test_reliable_source_is_marked_ok_and_trusted(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        record_fetch_attempt(
            session, data_type=DATA_TYPE_MARKET, scope_key=f"scope-{i}", requested_at=AS_OF,
            source_timestamp=AS_OF - timedelta(minutes=5), success=True,
        )

    report = compute_data_source_reliability_report(session)

    market = next(m for m in report.by_data_type if m.data_type == DATA_TYPE_MARKET)
    assert market.verdict == VERDICT_OK
    assert market.success_rate == Decimal("1")
    assert market.average_latency_seconds == Decimal("300")
    status = next(s for s in report.quality_statuses if s.key == DATA_TYPE_MARKET)
    assert status.trusted is True


def test_unreliable_source_is_marked_weak_and_untrusted(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        record_fetch_attempt(
            session, data_type=DATA_TYPE_MARKET, scope_key=f"scope-{i}", requested_at=AS_OF,
            source_timestamp=None, success=(i < total // 4), failure_reason=None if i < total // 4 else "boom",
        )

    report = compute_data_source_reliability_report(session)

    market = next(m for m in report.by_data_type if m.data_type == DATA_TYPE_MARKET)
    assert market.verdict == VERDICT_WEAK
    status = next(s for s in report.quality_statuses if s.key == DATA_TYPE_MARKET)
    assert status.trusted is False
    assert "below reliability threshold" in status.reason


def _make_prediction_with_evidence(session, symbol="AAA"):
    scan_date = AS_OF.date() + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=1000, source="test",
    ))
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    return prediction


def test_evidence_coverage_is_measured_per_category(session):
    _make_prediction_with_evidence(session)

    report = compute_data_source_reliability_report(session)

    fundamental = next(m for m in report.by_evidence_category if m.evidence_category == "FUNDAMENTAL")
    assert fundamental.available_count == 0
    assert fundamental.unavailable_count == 1
    assert fundamental.coverage_rate == Decimal("0")

    technical = next(m for m in report.by_evidence_category if m.evidence_category == "TECHNICAL_VOLUME")
    assert technical.available_count == 1
    assert technical.coverage_rate == Decimal("1")


def test_low_coverage_category_is_marked_untrusted(session):
    _make_prediction_with_evidence(session)

    report = compute_data_source_reliability_report(session)

    fundamental_status = next(s for s in report.quality_statuses if s.key == "FUNDAMENTAL")
    assert fundamental_status.trusted is False
    assert COVERAGE_TRUST_THRESHOLD > Decimal("0")


def test_report_never_writes_anything(session):
    prediction = _make_prediction_with_evidence(session)
    before = (prediction.opportunity_score, prediction.confidence)

    compute_data_source_reliability_report(session)

    after = (prediction.opportunity_score, prediction.confidence)
    assert before == after


def test_report_is_reproducible(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        record_fetch_attempt(
            session, data_type=DATA_TYPE_MARKET, scope_key=f"scope-{i}", requested_at=AS_OF,
            source_timestamp=AS_OF - timedelta(minutes=5), success=True,
        )
    _make_prediction_with_evidence(session)

    first = compute_data_source_reliability_report(session)
    second = compute_data_source_reliability_report(session)

    assert first == second
