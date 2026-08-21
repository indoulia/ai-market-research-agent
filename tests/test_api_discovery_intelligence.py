"""Contract tests for GET /api/v1/discovery/{summary,history,candidates}
(EPIC-M3.6)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth_session import create_session
from app.confidence_quality import QUALITY_HIGH
from app.db import Base
from app.discovery import SOURCE_CHATGPT, SOURCE_DAILY_UNIVERSE_SCAN, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import EVIDENCE_QUALITY_GATE_VERSION, STATE_SUFFICIENT
from app.lifecycle import LIFECYCLE_VERSION, STATE_ISSUED
from app.models import (
    DailyCandidateScan,
    EvidenceQualityDecision,
    Prediction,
    PredictionTrustScore,
    RecommendationLifecycle,
    RecommendationSelection,
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


def _make_scan(session, *, scan_date=None):
    scan_date = scan_date or (date(2027, 1, 1) + timedelta(days=next(_scan_counter)))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_stock(session, symbol="AAA", sector="TECH", industry="SOFTWARE", market_cap=Decimal("50000")):
    stock = Stock(symbol=symbol, exchange="NSE", sector=sector, industry=industry, company_name=f"{symbol} Ltd", market_cap=market_cap, is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _make_candidate(session, scan, stock, *, eligible=True, exclusion_reason=None, predicted_probability=Decimal("0.72"), volume_ratio_20d=Decimal("1.10")):
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=eligible, exclusion_reason=exclusion_reason,
        predicted_probability=predicted_probability, confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=volume_ratio_20d, atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    return candidate


def _make_discovered_only(session, *, symbol="DIS", sector="TECH", source=SOURCE_CHATGPT):
    """Discovered, never analyzed: no ScanCandidate at all."""
    scan = _make_scan(session)
    stock = _make_stock(session, symbol=symbol, sector=sector)
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=source, rationale="worth a look", discovered_at=AS_OF)
    session.commit()
    return scan, stock, discovery


def _make_ineligible(session, *, symbol="INE", sector="TECH"):
    scan = _make_scan(session)
    stock = _make_stock(session, symbol=symbol, sector=sector)
    _make_candidate(session, scan, stock, eligible=False, exclusion_reason="LOW_LIQUIDITY")
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_DAILY_UNIVERSE_SCAN, rationale="screened in", discovered_at=AS_OF)
    session.commit()
    return scan, stock, discovery


def _make_not_qualified(session, *, symbol="SUP", sector="TECH", source=SOURCE_CHATGPT):
    scan = _make_scan(session)
    stock = _make_stock(session, symbol=symbol, sector=sector)
    _make_candidate(session, scan, stock, predicted_probability=Decimal("0.10"))
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=source, rationale="looked promising", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    session.commit()
    return scan, stock, discovery, generation


def _make_qualified_discovery(session, *, symbol="AAA", sector="TECH", source=SOURCE_CHATGPT, market_cap=Decimal("50000"), scan=None):
    scan = scan or _make_scan(session)
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
    return scan, stock, discovery, generation


def _publish(session, scan, generation, *, rank=1):
    session.add(RecommendationSelection(
        scan_id=scan.id, recommendation_generation_id=generation.id, rank=rank, selected=True,
        selection_reason="TOP_RANKED", selection_rule_version="RS-001",
    ))
    session.commit()


# ---------------------------------------------------------------------------
# /discovery/summary
# ---------------------------------------------------------------------------


def test_summary_empty_state(client):
    response = client.get("/api/v1/discovery/summary")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["counts"] == {"discovered": 0, "analyzed": 0, "qualified": 0, "suppressed": 0, "published": 0}
    assert data["effectivenessBySource"] == []


def test_summary_counts_full_funnel(client, session):
    _make_discovered_only(session, symbol="DIS")
    _make_ineligible(session, symbol="INE")
    _make_not_qualified(session, symbol="SUP")
    scan, _, _, qualified_generation = _make_qualified_discovery(session, symbol="QUA")
    _, _, _, published_generation = _make_qualified_discovery(session, symbol="PUB")
    _publish(session, scan, published_generation)

    response = client.get("/api/v1/discovery/summary")
    counts = response.json()["data"]["counts"]

    assert counts["discovered"] == 5
    assert counts["suppressed"] == 2  # ineligible + not-qualified
    assert counts["qualified"] == 1
    assert counts["published"] == 1
    assert counts["analyzed"] == 4  # suppressed + qualified + published


def test_summary_effectiveness_by_source_reuses_m1_28_funnel(client, session):
    _make_qualified_discovery(session, symbol="AAA", source=SOURCE_CHATGPT)
    _make_not_qualified(session, symbol="BBB", source=SOURCE_CHATGPT)

    response = client.get("/api/v1/discovery/summary")
    by_source = {row["source"]: row for row in response.json()["data"]["effectivenessBySource"]}

    assert by_source[SOURCE_CHATGPT]["discoveredCount"] == 2
    assert by_source[SOURCE_CHATGPT]["qualifiedCount"] == 1
    assert by_source[SOURCE_CHATGPT]["rejectedCount"] == 1
    assert response.json()["data"]["effectivenessReportVersion"]


# ---------------------------------------------------------------------------
# /discovery/candidates
# ---------------------------------------------------------------------------


def test_candidates_discovered_stage(client, session):
    _make_discovered_only(session, symbol="DIS")

    response = client.get("/api/v1/discovery/candidates")
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["symbol"] == "DIS"
    assert items[0]["lifecycleStage"] == "DISCOVERED"
    assert items[0]["suppressionReason"] is None


def test_candidates_suppressed_ineligible_reason_hidden_without_auth(client, session):
    _make_ineligible(session, symbol="INE")

    response = client.get("/api/v1/discovery/candidates")
    item = response.json()["data"][0]
    assert item["lifecycleStage"] == "SUPPRESSED"
    assert item["suppressionReason"] is None  # not authenticated


def test_candidates_suppressed_reason_visible_with_auth(client, session):
    _make_ineligible(session, symbol="INE")
    auth_session = create_session(session, user_id="user-1", issued_at=AS_OF)

    response = client.get("/api/v1/discovery/candidates", headers={"Authorization": f"Bearer {auth_session.session_token}"})
    item = response.json()["data"][0]
    assert item["lifecycleStage"] == "SUPPRESSED"
    assert item["suppressionReason"] == "LOW_LIQUIDITY"


def test_candidates_suppressed_consensus_reason(client, session):
    _make_not_qualified(session, symbol="SUP")
    auth_session = create_session(session, user_id="user-1", issued_at=AS_OF)

    response = client.get("/api/v1/discovery/candidates", headers={"Authorization": f"Bearer {auth_session.session_token}"})
    item = response.json()["data"][0]
    assert item["lifecycleStage"] == "SUPPRESSED"
    assert item["suppressionReason"] == "model_probability"


def test_candidates_qualified_and_published_stages(client, session):
    scan, _, _, qualified_generation = _make_qualified_discovery(session, symbol="QUA")
    _, _, _, published_generation = _make_qualified_discovery(session, symbol="PUB")
    _publish(session, scan, published_generation)

    response = client.get("/api/v1/discovery/candidates")
    by_symbol = {i["symbol"]: i for i in response.json()["data"]}
    assert by_symbol["QUA"]["lifecycleStage"] == "QUALIFIED"
    assert by_symbol["PUB"]["lifecycleStage"] == "PUBLISHED"
    assert Decimal(by_symbol["QUA"]["score"]) > 0


def test_candidates_expose_candidate_id_and_published_recommendation_id(client, session):
    scan, _, _, qualified_generation = _make_qualified_discovery(session, symbol="QUA")
    _, _, _, published_generation = _make_qualified_discovery(session, symbol="PUB")
    _publish(session, scan, published_generation)

    response = client.get("/api/v1/discovery/candidates")
    by_symbol = {i["symbol"]: i for i in response.json()["data"]}

    assert isinstance(by_symbol["QUA"]["candidateId"], int)
    assert by_symbol["QUA"]["publishedRecommendationId"] is None
    assert by_symbol["PUB"]["publishedRecommendationId"] == published_generation.prediction_id


def test_candidates_discovered_date_range_filter(client, session):
    _make_discovered_only(session, symbol="OLD")
    scan2 = _make_scan(session, scan_date=date(2027, 3, 1))
    stock2 = _make_stock(session, symbol="NEW")
    record_discovery(session, scan_id=scan2.id, stock_id=stock2.id, source=SOURCE_CHATGPT, rationale="r", discovered_at=AS_OF + timedelta(days=60))
    session.commit()

    response = client.get(
        "/api/v1/discovery/candidates",
        params={"from": (AS_OF + timedelta(days=59)).date().isoformat()},
    )
    assert [i["symbol"] for i in response.json()["data"]] == ["NEW"]

    response = client.get(
        "/api/v1/discovery/candidates",
        params={"to": AS_OF.date().isoformat()},
    )
    assert [i["symbol"] for i in response.json()["data"]] == ["OLD"]


def test_candidates_discovery_sources_and_reasons_aggregate(client, session):
    scan = _make_scan(session)
    stock = _make_stock(session, symbol="AAA")
    _make_candidate(session, scan, stock)
    record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="chatgpt reason", discovered_at=AS_OF)
    record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_DAILY_UNIVERSE_SCAN, rationale="scan reason", discovered_at=AS_OF + timedelta(minutes=1))
    session.commit()

    response = client.get("/api/v1/discovery/candidates")
    item = response.json()["data"][0]
    assert set(item["discoverySources"]) == {SOURCE_CHATGPT, SOURCE_DAILY_UNIVERSE_SCAN}
    assert set(item["discoveryReasons"]) == {"chatgpt reason", "scan reason"}


def test_candidates_filter_by_sector_and_market_cap_and_basis(client, session):
    _make_qualified_discovery(session, symbol="AAA", sector="TECH", source=SOURCE_CHATGPT, market_cap=Decimal("50000"))
    _make_qualified_discovery(session, symbol="BBB", sector="PHARMA", source=SOURCE_DAILY_UNIVERSE_SCAN, market_cap=Decimal("1000"))

    sector_resp = client.get("/api/v1/discovery/candidates", params={"sector": "PHARMA"})
    assert [i["symbol"] for i in sector_resp.json()["data"]] == ["BBB"]

    bucket_resp = client.get("/api/v1/discovery/candidates", params={"marketCap": "LARGE_CAP"})
    assert [i["symbol"] for i in bucket_resp.json()["data"]] == ["AAA"]

    basis_resp = client.get("/api/v1/discovery/candidates", params={"discoveryBasis": SOURCE_DAILY_UNIVERSE_SCAN})
    assert [i["symbol"] for i in basis_resp.json()["data"]] == ["BBB"]


def test_candidates_cursor_pagination_covers_every_item_once(client, session):
    for i in range(5):
        _make_discovered_only(session, symbol=f"S{i}")

    seen = []
    cursor = None
    for _ in range(10):
        params = {"pageSize": 2}
        if cursor:
            params["cursor"] = cursor
        body = client.get("/api/v1/discovery/candidates", params=params).json()
        seen.extend(item["symbol"] for item in body["data"])
        cursor = body["meta"]["nextCursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


# ---------------------------------------------------------------------------
# /discovery/history
# ---------------------------------------------------------------------------


def test_history_empty_state(client):
    response = client.get("/api/v1/discovery/history")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_history_groups_by_scan_day(client, session):
    day1 = date(2027, 2, 1)
    day2 = date(2027, 2, 2)
    scan1 = _make_scan(session, scan_date=day1)
    scan2 = _make_scan(session, scan_date=day2)

    _make_qualified_discovery(session, symbol="Q1", scan=scan1)
    _make_not_qualified(session, symbol="S1")  # own scan, but let's target scan2 explicitly below instead

    # Build one more, precisely on scan2, that gets published on scan2.
    stock2 = _make_stock(session, symbol="P1")
    _make_candidate(session, scan2, stock2)
    discovery2 = record_discovery(session, scan_id=scan2.id, stock_id=stock2.id, source=SOURCE_CHATGPT, rationale="r", discovered_at=AS_OF)
    generation2 = route_discovery_through_pipeline(
        session, discovery2, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    session.commit()
    _publish(session, scan2, generation2)

    response = client.get("/api/v1/discovery/history", params={"days": 30})
    points = {p["scanDate"]: p for p in response.json()["data"]}

    assert points[day1.isoformat()]["discoveredCount"] == 1
    assert points[day1.isoformat()]["qualifiedCount"] == 1
    assert points[day2.isoformat()]["discoveredCount"] == 1
    assert points[day2.isoformat()]["publishedCount"] == 1
    # points are ordered oldest-first
    dates = [p["scanDate"] for p in response.json()["data"]]
    assert dates == sorted(dates)


def test_history_days_out_of_range_rejected(client):
    response = client.get("/api/v1/discovery/history", params={"days": 0})
    assert response.status_code == 422
