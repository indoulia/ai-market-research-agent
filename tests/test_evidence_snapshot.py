from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_snapshot import (
    ALL_EVIDENCE_CATEGORIES,
    EVIDENCE_CATEGORY_EVENT,
    EVIDENCE_CATEGORY_FUNDAMENTAL,
    EVIDENCE_CATEGORY_MARKET_SECTOR,
    EVIDENCE_CATEGORY_NEWS,
    EVIDENCE_CATEGORY_TECHNICAL_VOLUME,
    EVIDENCE_SNAPSHOT_VERSION,
    STATUS_AVAILABLE,
    STATUS_STALE,
    STATUS_UNAVAILABLE,
    RecommendationEvidenceImmutableError,
    capture_evidence_snapshot,
    get_evidence_snapshot,
)
from app.market_regime import classify_market_regime
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock

AS_OF = datetime(2026, 7, 10, tzinfo=timezone.utc)


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


def _make_scan(session, scan_date=date(2026, 7, 10)):
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_priced_stock(session, symbol, *, sector="Energy", price_timestamp=AS_OF):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector=sector)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=price_timestamp,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=1000, source="test",
    ))
    session.flush()
    return stock


def _make_qualified(session, scan, stock, *, discover=True):
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    if discover:
        discovery = record_discovery(
            session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT,
            rationale="strong technical breakout with rising volume", discovered_at=AS_OF,
        )
        generation = route_discovery_through_pipeline(
            session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
            target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
        )
    else:
        from app.recommendation_generator import generate_recommendation_for_candidate
        generation = generate_recommendation_for_candidate(
            session, candidate, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
            target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
        )
    return session.get(Prediction, generation.prediction_id)


def test_fundamental_and_event_are_always_unavailable(session):
    scan = _make_scan(session)
    stock = _make_priced_stock(session, "AAA")
    prediction = _make_qualified(session, scan, stock)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    by_category = {item.evidence_category: item for item in snapshot}
    assert by_category[EVIDENCE_CATEGORY_FUNDAMENTAL].status == STATUS_UNAVAILABLE
    assert by_category[EVIDENCE_CATEGORY_EVENT].status == STATUS_UNAVAILABLE


def test_every_category_is_captured_or_explicitly_unavailable(session):
    scan = _make_scan(session)
    stock = _make_priced_stock(session, "AAA")
    prediction = _make_qualified(session, scan, stock)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    assert {item.evidence_category for item in snapshot} == set(ALL_EVIDENCE_CATEGORIES)
    assert all(item.status in (STATUS_AVAILABLE, STATUS_STALE, STATUS_UNAVAILABLE) for item in snapshot)
    assert all(item.snapshot_rule_version == EVIDENCE_SNAPSHOT_VERSION for item in snapshot)


def test_technical_volume_evidence_is_fresh_when_market_price_is_current(session):
    scan = _make_scan(session)
    stock = _make_priced_stock(session, "AAA", price_timestamp=AS_OF)
    prediction = _make_qualified(session, scan, stock)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    technical = next(i for i in snapshot if i.evidence_category == EVIDENCE_CATEGORY_TECHNICAL_VOLUME)
    assert technical.status == STATUS_AVAILABLE
    assert technical.is_stale is False
    assert "sma20_distance" in technical.reference


def test_technical_volume_evidence_is_stale_when_market_price_is_old(session):
    scan = _make_scan(session)
    stock = _make_priced_stock(session, "AAA", price_timestamp=AS_OF - timedelta(days=5))
    prediction = _make_qualified(session, scan, stock)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    technical = next(i for i in snapshot if i.evidence_category == EVIDENCE_CATEGORY_TECHNICAL_VOLUME)
    assert technical.status == STATUS_STALE
    assert technical.is_stale is True


def test_technical_volume_evidence_is_unavailable_with_no_market_price(session):
    scan = _make_scan(session)
    stock = Stock(symbol="NOPRICE", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    prediction = _make_qualified(session, scan, stock)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    technical = next(i for i in snapshot if i.evidence_category == EVIDENCE_CATEGORY_TECHNICAL_VOLUME)
    assert technical.status == STATUS_UNAVAILABLE


def test_news_evidence_captures_discovery_rationale(session):
    scan = _make_scan(session)
    stock = _make_priced_stock(session, "AAA")
    prediction = _make_qualified(session, scan, stock, discover=True)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    news = next(i for i in snapshot if i.evidence_category == EVIDENCE_CATEGORY_NEWS)
    assert news.status == STATUS_AVAILABLE
    assert news.reference == "strong technical breakout with rising volume"
    assert news.source == f"DISCOVERY:{SOURCE_CHATGPT}"


def test_news_evidence_unavailable_without_a_discovery_record(session):
    scan = _make_scan(session)
    stock = _make_priced_stock(session, "AAA")
    prediction = _make_qualified(session, scan, stock, discover=False)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    news = next(i for i in snapshot if i.evidence_category == EVIDENCE_CATEGORY_NEWS)
    assert news.status == STATUS_UNAVAILABLE


def test_market_sector_evidence_includes_sector_and_regime_where_classified(session):
    scan = _make_scan(session)
    stock = _make_priced_stock(session, "AAA", sector="Energy")
    prediction = _make_qualified(session, scan, stock)
    classify_market_regime(session, scan.id)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    market = next(i for i in snapshot if i.evidence_category == EVIDENCE_CATEGORY_MARKET_SECTOR)
    assert market.status == STATUS_AVAILABLE
    assert "sector=Energy" in market.reference
    assert "regime=" in market.reference


def test_market_sector_evidence_available_from_sector_alone_without_regime(session):
    scan = _make_scan(session)
    stock = _make_priced_stock(session, "AAA", sector="Energy")
    prediction = _make_qualified(session, scan, stock)
    # deliberately not calling classify_market_regime

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    market = next(i for i in snapshot if i.evidence_category == EVIDENCE_CATEGORY_MARKET_SECTOR)
    assert market.status == STATUS_AVAILABLE
    assert "sector=Energy" in market.reference
    assert "regime=" not in market.reference


def test_snapshot_is_idempotent_and_immutable(session):
    scan = _make_scan(session)
    stock = _make_priced_stock(session, "AAA")
    prediction = _make_qualified(session, scan, stock)

    first = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    second = capture_evidence_snapshot(session, prediction, captured_at=AS_OF + timedelta(days=1))

    assert [i.id for i in first] == [i.id for i in second]

    item = next(i for i in first if i.evidence_category == EVIDENCE_CATEGORY_TECHNICAL_VOLUME)
    assert item.status == STATUS_AVAILABLE
    item.status = STATUS_STALE
    with pytest.raises(RecommendationEvidenceImmutableError, match="status"):
        session.flush()
    session.rollback()


def test_get_evidence_snapshot_retrieves_the_complete_snapshot(session):
    scan = _make_scan(session)
    stock = _make_priced_stock(session, "AAA")
    prediction = _make_qualified(session, scan, stock)
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    retrieved = get_evidence_snapshot(session, prediction.id)

    assert len(retrieved) == len(ALL_EVIDENCE_CATEGORIES)
    assert [i.evidence_category for i in retrieved] == list(ALL_EVIDENCE_CATEGORIES)
