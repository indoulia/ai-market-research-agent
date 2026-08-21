"""Contract tests for GET /api/v1/discoveries, /market/summary, /news and
/events (EPIC-M1.139)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.confidence_quality import QUALITY_HIGH
from app.db import Base
from app.discovery import SOURCE_CHATGPT, SOURCE_DAILY_UNIVERSE_SCAN, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import EVIDENCE_QUALITY_GATE_VERSION, STATE_SUFFICIENT
from app.lifecycle import STATE_ISSUED, LIFECYCLE_VERSION
from app.models import (
    CorporateAction,
    DailyCandidateScan,
    EvidenceQualityDecision,
    MarketPrice,
    MarketRegime,
    NewsEventRecord,
    Prediction,
    PredictionTrustScore,
    RecommendationLifecycle,
    ScanCandidate,
    Stock,
)
from app.opportunity_ranking import rank_positive_opportunities
from app.positive_recommendation_gate import evaluate_positive_gate
from app.prediction_trust_score import PREDICTION_TRUST_SCORE_VERSION

from api.deps import get_db
from app.main import app

AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
MODEL_VERSION = "test-model-1"
_scan_counter = iter(range(100000))


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _make_scan(session):
    scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_stock(session, symbol="AAA", sector="TECH", industry="SOFTWARE", market_cap=Decimal("50000")):
    stock = Stock(symbol=symbol, exchange="NSE", sector=sector, industry=industry, company_name=f"{symbol} Ltd", market_cap=market_cap, is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _make_candidate(session, scan, stock, *, volume_ratio_20d=Decimal("1.10")):
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=volume_ratio_20d, atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    return candidate


def _make_qualified_discovery(session, *, symbol="AAA", sector="TECH", source=SOURCE_CHATGPT, market_cap=Decimal("50000")):
    scan = _make_scan(session)
    stock = _make_stock(session, symbol=symbol, sector=sector, market_cap=market_cap)
    _make_candidate(session, scan, stock)
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=source, rationale=f"{source} likes it", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    session.add(EvidenceQualityDecision(
        prediction_id=prediction.id, state=STATE_SUFFICIENT, available_category_count=2, stale_category_count=0,
        unavailable_category_count=3, categories_considered=["TECHNICAL_VOLUME", "NEWS"], leaked_categories=[],
        reasons=[], confidence_adjustment_ceiling=prediction.confidence, blocks_publication=False,
        evaluated_at=AS_OF, gate_rule_version=EVIDENCE_QUALITY_GATE_VERSION,
    ))
    session.add(PredictionTrustScore(
        prediction_id=prediction.id, overall_trust_score=Decimal("0.9"), trust_quality=QUALITY_HIGH,
        calibration_component=None, historical_accuracy_component=None, recent_performance_component=None,
        horizon_reliability_component=None, regime_reliability_component=None, evidence_quality_component=None,
        available_component_count=1, reasons=[], computed_at=AS_OF, trust_score_version=PREDICTION_TRUST_SCORE_VERSION,
    ))
    session.commit()
    evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)
    rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)
    session.add(RecommendationLifecycle(
        recommendation_generation_id=generation.id, state=STATE_ISSUED, lifecycle_rule_version=LIFECYCLE_VERSION, check_count=0,
    ))
    session.commit()
    return stock, discovery, generation


def test_discoveries_empty(client):
    response = client.get("/api/v1/discoveries")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_discoveries_pending_analysis_for_never_routed_candidate(client, session):
    scan = _make_scan(session)
    stock = _make_stock(session, symbol="AAA")
    _make_candidate(session, scan, stock)
    record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="looks interesting", discovered_at=AS_OF)
    session.commit()

    response = client.get("/api/v1/discoveries")
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["symbol"] == "AAA"
    assert items[0]["status"] == "PENDING_ANALYSIS"
    assert items[0]["score"] is None
    assert items[0]["discoveryReasons"] == ["looks interesting"]


def test_discoveries_qualified_shows_score_and_status(client, session):
    stock, discovery, generation = _make_qualified_discovery(session)

    response = client.get("/api/v1/discoveries")
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["status"] == STATE_ISSUED
    assert Decimal(items[0]["score"]) > 0
    assert items[0]["trustScore"] == "0.90000000"
    assert items[0]["marketCapBucket"] == "LARGE_CAP"  # 50000 crore >= 20000 threshold
    assert items[0]["liquidity"] == "NORMAL"  # volume_ratio_20d=1.10 -> NORMAL bucket


def test_discoveries_aggregates_reasons_across_sources(client, session):
    scan = _make_scan(session)
    stock = _make_stock(session, symbol="AAA")
    _make_candidate(session, scan, stock)
    record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="chatgpt reason", discovered_at=AS_OF)
    record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_DAILY_UNIVERSE_SCAN, rationale="scan reason", discovered_at=AS_OF + timedelta(minutes=1))
    session.commit()

    response = client.get("/api/v1/discoveries")
    items = response.json()["data"]
    assert len(items) == 1
    assert set(items[0]["discoveryReasons"]) == {"chatgpt reason", "scan reason"}


def test_discoveries_sector_filter(client, session):
    _make_qualified_discovery(session, symbol="AAA", sector="TECH")
    scan = _make_scan(session)
    stock2 = _make_stock(session, symbol="BBB", sector="PHARMA")
    _make_candidate(session, scan, stock2)
    record_discovery(session, scan_id=scan.id, stock_id=stock2.id, source=SOURCE_CHATGPT, rationale="r", discovered_at=AS_OF)
    session.commit()

    response = client.get("/api/v1/discoveries", params={"sector": "PHARMA"})
    items = response.json()["data"]
    assert [i["symbol"] for i in items] == ["BBB"]


def test_discoveries_market_cap_bucket_filter(client, session):
    _make_qualified_discovery(session, symbol="SMALL", market_cap=Decimal("1000"))
    scan = _make_scan(session)
    stock2 = _make_stock(session, symbol="LARGE", market_cap=Decimal("50000"))
    _make_candidate(session, scan, stock2)
    record_discovery(session, scan_id=scan.id, stock_id=stock2.id, source=SOURCE_CHATGPT, rationale="r", discovered_at=AS_OF)
    session.commit()

    response = client.get("/api/v1/discoveries", params={"marketCapBucket": "LARGE_CAP"})
    items = response.json()["data"]
    assert [i["symbol"] for i in items] == ["LARGE"]


def test_discoveries_unknown_sort_rejected(client):
    response = client.get("/api/v1/discoveries", params={"sort": "bogus"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_discoveries_cursor_pagination_covers_every_item_once(client, session):
    for i in range(5):
        scan = _make_scan(session)
        stock = _make_stock(session, symbol=f"S{i}")
        _make_candidate(session, scan, stock)
        record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="r", discovered_at=AS_OF + timedelta(days=i))
    session.commit()

    seen = []
    cursor = None
    for _ in range(10):
        params = {"pageSize": 2}
        if cursor:
            params["cursor"] = cursor
        body = client.get("/api/v1/discoveries", params=params).json()
        seen.extend(item["symbol"] for item in body["data"])
        cursor = body["meta"]["nextCursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


def test_market_summary_empty_state(client):
    response = client.get("/api/v1/market/summary")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["marketStatus"] == "UNKNOWN"
    assert data["regime"] is None
    assert data["indexes"] == []
    assert data["sectorLeaders"] == []


def test_market_summary_with_regime_and_sector_moves(client, session):
    scan = _make_scan(session)
    stock_a = _make_stock(session, symbol="AAA", sector="TECH")
    stock_b = _make_stock(session, symbol="BBB", sector="PHARMA")
    session.add_all([
        MarketPrice(stock_id=stock_a.id, timestamp=AS_OF, open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"), volume=1000, source="test"),
        MarketPrice(stock_id=stock_b.id, timestamp=AS_OF, open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"), volume=2000, source="test"),
        MarketPrice(stock_id=stock_a.id, timestamp=AS_OF + timedelta(days=1), open=Decimal("100"), high=Decimal("110"), low=Decimal("100"), close=Decimal("110"), volume=1500, source="test"),
        MarketPrice(stock_id=stock_b.id, timestamp=AS_OF + timedelta(days=1), open=Decimal("100"), high=Decimal("95"), low=Decimal("95"), close=Decimal("95"), volume=2500, source="test"),
        MarketRegime(scan_id=scan.id, regime="RISK_ON", breadth_positive_ratio=Decimal("0.6500"), average_atr_percent=Decimal("0.028"), eligible_count=10, regime_rule_version="MRG-001"),
    ])
    session.commit()

    response = client.get("/api/v1/market/summary")
    data = response.json()["data"]
    assert data["regime"] == "RISK_ON"
    assert data["advanceDecline"] == "0.6500"
    assert data["volume"] == 4000
    assert data["sectorLeaders"][0]["sector"] == "TECH"
    assert data["sectorLaggards"][0]["sector"] == "PHARMA"


def test_news_list_and_symbol_filter(client, session):
    stock_a = _make_stock(session, symbol="AAA")
    stock_b = _make_stock(session, symbol="BBB")
    session.add_all([
        NewsEventRecord(stock_id=stock_a.id, source="test", external_id="n1", headline="AAA news", event_type="GENERAL", materiality="LOW", published_at=AS_OF, fetched_at=AS_OF, ingestion_rule_version="NEV-001"),
        NewsEventRecord(stock_id=stock_b.id, source="test", external_id="n2", headline="BBB news", event_type="GENERAL", materiality="HIGH", published_at=AS_OF, fetched_at=AS_OF, ingestion_rule_version="NEV-001"),
    ])
    session.commit()

    response = client.get("/api/v1/news", params={"symbol": "AAA"})
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["headline"] == "AAA news"
    assert items[0]["affectedSecurities"] == ["AAA"]


def test_events_list_from_corporate_actions(client, session):
    stock = _make_stock(session, symbol="AAA")
    session.add(CorporateAction(
        stock_id=stock.id, action_type="DIVIDEND", effective_date=AS_OF.date(), ratio=None, cash_amount=Decimal("2.5"),
        old_symbol=None, new_symbol=None, source="test", action_version="CA-001", recorded_at=AS_OF,
    ))
    session.commit()

    response = client.get("/api/v1/events")
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["symbol"] == "AAA"
    assert items[0]["type"] == "DIVIDEND"
    assert items[0]["evidenceId"]
