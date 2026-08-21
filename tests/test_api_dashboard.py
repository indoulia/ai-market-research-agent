"""Contract tests for GET /api/v1/dashboard/snapshot (EPIC-M3.2)."""

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
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import EVIDENCE_QUALITY_GATE_VERSION, STATE_SUFFICIENT
from app.lifecycle import LIFECYCLE_VERSION, STATE_ISSUED
from app.models import (
    CorporateAction,
    DailyCandidateScan,
    EvidenceQualityDecision,
    MarketPrice,
    NewsEventRecord,
    Prediction,
    PredictionTrustScore,
    RecommendationGeneration,
    RecommendationLifecycle,
    ScanCandidate,
    Stock,
)
from app.opportunity_ranking import rank_positive_opportunities
from app.outcomes import evaluate_recommendation
from app.positive_recommendation_gate import evaluate_positive_gate
from app.prediction_trust_score import PREDICTION_TRUST_SCORE_VERSION

from api.deps import get_db
from api.rate_limit import default_limiter
from app.main import app

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
_scan_counter = iter(range(100000))


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    # `api.rate_limit.default_limiter` is a process-wide singleton keyed by
    # client host (EPIC-M1.132), shared by every test file that hits the
    # app through `TestClient` in the same pytest process. This file adds
    # enough extra requests to occasionally push a *later* test file's own
    # requests over the fixed-window limit within the same 60s window --
    # pre-existing shared test-infra state, not this EPIC's to fix broadly.
    # Resetting it before and after each test here keeps this file's own
    # request volume from leaking into other test files' budget.
    default_limiter._hits.clear()
    yield
    default_limiter._hits.clear()


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


def _make_prediction(session, symbol="AAA", sector="TECH", target_return=Decimal("0.05"), market_cap=Decimal("1000000000"), as_of=AS_OF):
    scan_date = as_of.date() + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", sector=sector, company_name=f"{symbol} Ltd", market_cap=market_cap, is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=as_of,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=1000, source="test",
    ))
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=as_of)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
        target_return=target_return, stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    return prediction, generation, stock, scan


def _add_evidence_quality(session, prediction, state=STATE_SUFFICIENT, as_of=AS_OF):
    session.add(EvidenceQualityDecision(
        prediction_id=prediction.id, state=state, available_category_count=2, stale_category_count=0,
        unavailable_category_count=3, categories_considered=["TECHNICAL_VOLUME", "NEWS"], leaked_categories=[],
        reasons=[], confidence_adjustment_ceiling=prediction.confidence, blocks_publication=(state != STATE_SUFFICIENT),
        evaluated_at=as_of, gate_rule_version=EVIDENCE_QUALITY_GATE_VERSION,
    ))
    session.commit()


def _add_trust_score(session, prediction, score=Decimal("0.9"), as_of=AS_OF):
    session.add(PredictionTrustScore(
        prediction_id=prediction.id, overall_trust_score=score, trust_quality=QUALITY_HIGH,
        calibration_component=None, historical_accuracy_component=None, recent_performance_component=None,
        horizon_reliability_component=None, regime_reliability_component=None, evidence_quality_component=None,
        available_component_count=1, reasons=[], computed_at=as_of, trust_score_version=PREDICTION_TRUST_SCORE_VERSION,
    ))
    session.commit()


def _add_lifecycle(session, generation, state=STATE_ISSUED):
    lifecycle = RecommendationLifecycle(
        recommendation_generation_id=generation.id, state=state, lifecycle_rule_version=LIFECYCLE_VERSION, check_count=0,
    )
    session.add(lifecycle)
    session.commit()
    return lifecycle


def _make_gate_passed(session, *, symbol="AAA", sector="TECH", target_return=Decimal("0.05"), trust_score=Decimal("0.9"), market_cap=Decimal("1000000000"), as_of=AS_OF):
    prediction, generation, stock, _scan = _make_prediction(session, symbol=symbol, sector=sector, target_return=target_return, market_cap=market_cap, as_of=as_of)
    _add_evidence_quality(session, prediction, as_of=as_of)
    _add_trust_score(session, prediction, score=trust_score, as_of=as_of)
    evaluate_positive_gate(session, prediction, evaluated_at=as_of)
    return prediction, generation, stock


def _rank_and_activate(session, entries, *, evaluated_at=AS_OF):
    predictions = [prediction for prediction, _generation, _stock in entries]
    rank_positive_opportunities(session, [p.id for p in predictions], evaluated_at=evaluated_at)
    for _prediction, generation, _stock in entries:
        _add_lifecycle(session, generation)
    return entries


def _make_ranked_recommendation(session, **kwargs):
    entry = _make_gate_passed(session, **kwargs)
    _rank_and_activate(session, [entry])
    return entry


def test_empty_dashboard_returns_honest_defaults(client):
    response = client.get("/api/v1/dashboard/snapshot")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["marketStatus"] == "UNKNOWN"
    assert data["marketRegime"] is None
    assert data["indices"] == []
    assert data["topOpportunities"] == []
    assert data["recentChanges"] == []
    assert data["importantEvents"] == []
    assert data["trustSummary"]["sampleSize"] == 0
    assert data["trustSummary"]["smallSample"] is True
    assert data["trustSummary"]["trustScore"] is None
    assert data["dataFreshness"]["opportunitiesAsOf"] is None
    assert data["dataFreshness"]["newsAsOf"] is None
    assert data["dataFreshness"]["marketAsOf"]


def test_top_opportunities_full_field_shape(client, session):
    prediction, generation, stock = _make_ranked_recommendation(session)

    response = client.get("/api/v1/dashboard/snapshot")
    assert response.status_code == 200
    items = response.json()["data"]["topOpportunities"]
    assert len(items) == 1
    item = items[0]
    assert item["id"] == generation.id
    assert item["symbol"] == "AAA"
    assert item["name"] == "AAA Ltd"
    assert item["horizon"] == prediction.horizon_days
    assert item["status"] == STATE_ISSUED
    assert item["trustScore"] == "0.90000000"
    assert Decimal(item["score"]) > 0
    assert Decimal(item["upsidePercent"]) > 0
    assert item["updatedAt"]


def test_name_falls_back_to_symbol_when_company_name_missing(client, session):
    entry = _make_gate_passed(session, symbol="ZZZ")
    _rank_and_activate(session, [entry])
    _, _, stock = entry
    stock.company_name = None
    session.commit()

    response = client.get("/api/v1/dashboard/snapshot")
    item = response.json()["data"]["topOpportunities"][0]
    assert item["name"] == "ZZZ"


def test_top_opportunities_only_include_positive_open_lifecycle(client, session):
    passed = _make_gate_passed(session, symbol="AAA")
    prediction, generation, stock, _scan = _make_prediction(session, symbol="BBB")
    not_passed = (prediction, generation, stock)
    _rank_and_activate(session, [passed, not_passed])

    response = client.get("/api/v1/dashboard/snapshot")
    symbols = [item["symbol"] for item in response.json()["data"]["topOpportunities"]]
    assert symbols == ["AAA"]


def test_top_opportunities_ordered_by_score_descending(client, session):
    low = _make_gate_passed(session, symbol="LOW", target_return=Decimal("0.02"), trust_score=Decimal("0.3"))
    high = _make_gate_passed(session, symbol="HIGH", target_return=Decimal("0.15"), trust_score=Decimal("0.95"))
    _rank_and_activate(session, [low, high])

    response = client.get("/api/v1/dashboard/snapshot")
    symbols = [item["symbol"] for item in response.json()["data"]["topOpportunities"]]
    assert symbols == ["HIGH", "LOW"]


def test_recent_changes_ordered_by_updated_at_not_score(client, session):
    low_score = _make_gate_passed(session, symbol="OLDCHANGE", target_return=Decimal("0.15"), trust_score=Decimal("0.95"))
    high_score = _make_gate_passed(session, symbol="NEWCHANGE", target_return=Decimal("0.02"), trust_score=Decimal("0.3"))
    _rank_and_activate(session, [low_score, high_score])

    # Force NEWCHANGE's lifecycle to look more recently updated than OLDCHANGE's,
    # even though it scores lower -- recentChanges must reflect recency, not score.
    _old_gen = low_score[1]
    new_gen = high_score[1]
    old_lifecycle = session.query(RecommendationLifecycle).filter_by(recommendation_generation_id=_old_gen.id).one()
    new_lifecycle = session.query(RecommendationLifecycle).filter_by(recommendation_generation_id=new_gen.id).one()
    old_lifecycle.last_checked_at = AS_OF
    new_lifecycle.last_checked_at = AS_OF + timedelta(days=1)
    session.commit()

    response = client.get("/api/v1/dashboard/snapshot")
    data = response.json()["data"]
    assert [item["symbol"] for item in data["topOpportunities"]] == ["OLDCHANGE", "NEWCHANGE"]
    assert [item["symbol"] for item in data["recentChanges"]] == ["NEWCHANGE", "OLDCHANGE"]


def test_market_and_horizon_filters_apply_to_opportunities(client, session):
    aaa = _make_gate_passed(session, symbol="AAA")
    bbb = _make_gate_passed(session, symbol="BBB")
    _rank_and_activate(session, [aaa, bbb])
    bbb_horizon = bbb[0].horizon_days

    response = client.get("/api/v1/dashboard/snapshot", params={"horizon": bbb_horizon})
    symbols = [item["symbol"] for item in response.json()["data"]["topOpportunities"]]
    assert "BBB" in symbols

    response = client.get("/api/v1/dashboard/snapshot", params={"market": "nse"})
    symbols = [item["symbol"] for item in response.json()["data"]["topOpportunities"]]
    assert set(symbols) == {"AAA", "BBB"}

    response = client.get("/api/v1/dashboard/snapshot", params={"market": "bse"})
    assert response.json()["data"]["topOpportunities"] == []


def test_sector_and_size_quick_filters_apply_to_opportunities(client, session):
    small = _make_gate_passed(session, symbol="SMALL", sector="S1", market_cap=Decimal("1000"))
    large = _make_gate_passed(session, symbol="LARGE", sector="S2", market_cap=Decimal("50000"))
    _rank_and_activate(session, [small, large])

    response = client.get("/api/v1/dashboard/snapshot", params={"sector": "S1"})
    symbols = [item["symbol"] for item in response.json()["data"]["topOpportunities"]]
    assert symbols == ["SMALL"]

    response = client.get("/api/v1/dashboard/snapshot", params={"marketCapBucket": "LARGE_CAP"})
    symbols = [item["symbol"] for item in response.json()["data"]["topOpportunities"]]
    assert symbols == ["LARGE"]


def test_limit_bounds_opportunities_and_changes(client, session):
    entries = [_make_gate_passed(session, symbol=f"S{i}", sector=f"SECTOR{i}") for i in range(5)]
    _rank_and_activate(session, entries)

    response = client.get("/api/v1/dashboard/snapshot", params={"limit": 2})
    data = response.json()["data"]
    assert len(data["topOpportunities"]) == 2
    assert len(data["recentChanges"]) == 2


def test_market_summary_fields_pass_through_to_snapshot(client, session):
    scan = DailyCandidateScan(scan_date=date(2027, 1, 1), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    from app.models import MarketRegime
    session.add(MarketRegime(scan_id=scan.id, regime="RISK_ON", breadth_positive_ratio=Decimal("0.6500"), average_atr_percent=Decimal("0.028"), eligible_count=10, regime_rule_version="MRG-001"))
    session.commit()

    response = client.get("/api/v1/dashboard/snapshot")
    data = response.json()["data"]
    assert data["marketRegime"] == "RISK_ON"
    assert data["marketStatus"] == "UNKNOWN"
    assert data["indices"] == []


def test_important_events_merge_news_and_events_by_recency(client, session):
    stock = Stock(symbol="AAA", exchange="NSE", sector="TECH", company_name="AAA Ltd", market_cap=Decimal("1000"), is_active=True)
    session.add(stock)
    session.flush()
    session.add(NewsEventRecord(
        stock_id=stock.id, source="test", external_id="n1", headline="Older news", event_type="GENERAL",
        materiality="LOW", published_at=AS_OF, fetched_at=AS_OF, ingestion_rule_version="NEV-001",
    ))
    session.add(CorporateAction(
        stock_id=stock.id, action_type="DIVIDEND", effective_date=(AS_OF + timedelta(days=1)).date(), ratio=None,
        cash_amount=Decimal("2.5"), old_symbol=None, new_symbol=None, source="test", action_version="CA-001",
        recorded_at=AS_OF + timedelta(days=1),
    ))
    session.commit()

    response = client.get("/api/v1/dashboard/snapshot")
    events = response.json()["data"]["importantEvents"]
    assert [e["kind"] for e in events] == ["CORPORATE_ACTION", "NEWS"]
    assert events[0]["symbol"] == "AAA"
    assert events[1]["title"] == "Older news"


def test_trust_summary_reflects_tracking_summary_window(client, session):
    now = datetime.now(timezone.utc)
    prediction, generation, stock, _scan = _make_prediction(session, symbol="AAA", as_of=now - timedelta(days=1))
    _add_trust_score(session, prediction, score=Decimal("0.8"), as_of=now)

    for day in range(1, prediction.horizon_days + 1):
        session.add(MarketPrice(
            stock_id=stock.id, timestamp=now - timedelta(days=1) + timedelta(days=day),
            open=Decimal("100"), high=Decimal("106"), low=Decimal("99"), close=Decimal("105"), volume=1000, source="test",
        ))
    session.commit()
    evaluate_recommendation(session, prediction)
    session.commit()

    response = client.get("/api/v1/dashboard/snapshot")
    trust_summary = response.json()["data"]["trustSummary"]
    assert trust_summary["sampleSize"] == 1
    assert trust_summary["trustScore"] == "0.80000000"
    assert trust_summary["modelVersion"] == MODEL_VERSION
