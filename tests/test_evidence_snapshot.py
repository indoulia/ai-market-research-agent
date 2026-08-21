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


def test_fundamental_without_ingested_data_and_event_are_unavailable(session):
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


def test_fundamental_evidence_is_available_when_ingested_and_fresh(session):
    from app.fundamental_data.ingest import FUNDAMENTAL_INGESTION_VERSION
    from app.models import FundamentalDataRecord

    scan = _make_scan(session)
    stock = _make_priced_stock(session, "BBB")
    session.add(FundamentalDataRecord(
        stock_id=stock.id, source="yahoo-finance", period_end_date=None, revenue=Decimal("1000"),
        net_income=Decimal("100"), eps=Decimal("2.5"), gross_margin=Decimal("0.4"), operating_margin=None,
        net_margin=None, debt_to_equity=None, free_cash_flow=None, pe_ratio=None, price_to_book=None,
        published_at=AS_OF - timedelta(days=10), fetched_at=AS_OF - timedelta(days=10),
        ingestion_rule_version=FUNDAMENTAL_INGESTION_VERSION,
    ))
    session.commit()
    prediction = _make_qualified(session, scan, stock)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    fundamental = {item.evidence_category: item for item in snapshot}[EVIDENCE_CATEGORY_FUNDAMENTAL]
    assert fundamental.status == STATUS_AVAILABLE
    assert fundamental.source == "yahoo-finance"
    assert "revenue=1000" in fundamental.reference


def test_fundamental_evidence_is_stale_beyond_the_freshness_window(session):
    from app.fundamental_data.ingest import FUNDAMENTAL_INGESTION_VERSION
    from app.models import FundamentalDataRecord

    scan = _make_scan(session)
    stock = _make_priced_stock(session, "CCC")
    session.add(FundamentalDataRecord(
        stock_id=stock.id, source="yahoo-finance", period_end_date=None, revenue=Decimal("1000"),
        net_income=None, eps=None, gross_margin=None, operating_margin=None, net_margin=None,
        debt_to_equity=None, free_cash_flow=None, pe_ratio=None, price_to_book=None,
        published_at=AS_OF - timedelta(days=200), fetched_at=AS_OF - timedelta(days=200),
        ingestion_rule_version=FUNDAMENTAL_INGESTION_VERSION,
    ))
    session.commit()
    prediction = _make_qualified(session, scan, stock)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    fundamental = {item.evidence_category: item for item in snapshot}[EVIDENCE_CATEGORY_FUNDAMENTAL]
    assert fundamental.status == STATUS_STALE
    assert fundamental.is_stale is True


def test_fundamental_evidence_ignores_data_published_after_the_decision(session):
    from app.fundamental_data.ingest import FUNDAMENTAL_INGESTION_VERSION
    from app.models import FundamentalDataRecord

    scan = _make_scan(session)
    stock = _make_priced_stock(session, "DDD")
    session.add(FundamentalDataRecord(
        stock_id=stock.id, source="yahoo-finance", period_end_date=None, revenue=Decimal("5000"),
        net_income=None, eps=None, gross_margin=None, operating_margin=None, net_margin=None,
        debt_to_equity=None, free_cash_flow=None, pe_ratio=None, price_to_book=None,
        published_at=AS_OF + timedelta(days=5), fetched_at=AS_OF + timedelta(days=5),
        ingestion_rule_version=FUNDAMENTAL_INGESTION_VERSION,
    ))
    session.commit()
    prediction = _make_qualified(session, scan, stock)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    fundamental = {item.evidence_category: item for item in snapshot}[EVIDENCE_CATEGORY_FUNDAMENTAL]
    assert fundamental.status == STATUS_UNAVAILABLE


def _add_news_event(session, stock, *, external_id, headline, event_type, materiality, published_at):
    from app.news_data.ingest import NEWS_EVENT_INGESTION_VERSION
    from app.models import NewsEventRecord

    record = NewsEventRecord(
        stock_id=stock.id, source="yahoo-finance", external_id=external_id, headline=headline,
        event_type=event_type, materiality=materiality, published_at=published_at, fetched_at=published_at,
        ingestion_rule_version=NEWS_EVENT_INGESTION_VERSION,
    )
    session.add(record)
    session.commit()
    return record


def test_news_evidence_prefers_real_ingested_data_over_discovery_rationale(session):
    from app.news_data.ingest import EVENT_TYPE_NEWS_STORY, MATERIALITY_LOW

    scan = _make_scan(session)
    stock = _make_priced_stock(session, "EEE")
    _add_news_event(
        session, stock, external_id="n1", headline="Real ingested market commentary",
        event_type=EVENT_TYPE_NEWS_STORY, materiality=MATERIALITY_LOW, published_at=AS_OF - timedelta(hours=1),
    )
    prediction = _make_qualified(session, scan, stock)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    news = {item.evidence_category: item for item in snapshot}[EVIDENCE_CATEGORY_NEWS]
    assert news.status == STATUS_AVAILABLE
    assert news.source == "yahoo-finance"
    assert news.reference == "Real ingested market commentary"


def test_news_evidence_falls_back_to_discovery_rationale_without_real_data(session):
    scan = _make_scan(session)
    stock = _make_priced_stock(session, "FFF")
    prediction = _make_qualified(session, scan, stock)  # discovery-based, no NewsEventRecord seeded

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    news = {item.evidence_category: item for item in snapshot}[EVIDENCE_CATEGORY_NEWS]
    assert news.status == STATUS_AVAILABLE
    assert news.source.startswith("DISCOVERY:")


def test_event_evidence_is_available_for_a_real_corporate_event(session):
    from app.news_data.ingest import EVENT_TYPE_CORPORATE_EVENT, MATERIALITY_HIGH

    scan = _make_scan(session)
    stock = _make_priced_stock(session, "GGG")
    _add_news_event(
        session, stock, external_id="e1", headline="Company announces merger agreement",
        event_type=EVENT_TYPE_CORPORATE_EVENT, materiality=MATERIALITY_HIGH, published_at=AS_OF - timedelta(hours=1),
    )
    prediction = _make_qualified(session, scan, stock)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    event = {item.evidence_category: item for item in snapshot}[EVIDENCE_CATEGORY_EVENT]
    assert event.status == STATUS_AVAILABLE
    assert "merger" in event.reference.lower()
    assert "materiality=HIGH" in event.reference


def test_event_evidence_ignores_a_corporate_event_published_after_the_decision(session):
    from app.news_data.ingest import EVENT_TYPE_CORPORATE_EVENT, MATERIALITY_HIGH

    scan = _make_scan(session)
    stock = _make_priced_stock(session, "HHH")
    _add_news_event(
        session, stock, external_id="e2", headline="Company announces merger agreement",
        event_type=EVENT_TYPE_CORPORATE_EVENT, materiality=MATERIALITY_HIGH, published_at=AS_OF + timedelta(hours=5),
    )
    prediction = _make_qualified(session, scan, stock)

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    event = {item.evidence_category: item for item in snapshot}[EVIDENCE_CATEGORY_EVENT]
    assert event.status == STATUS_UNAVAILABLE
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
