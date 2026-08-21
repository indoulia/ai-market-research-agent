"""Contract tests for the /api/v1/recommendations/{id} detail/history/
events/outcome endpoints (EPIC-M1.137)."""

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
    EvidenceRevalidationCheck,
    MarketPrice,
    NewsEventRecord,
    Prediction,
    PredictionTrustScore,
    RecommendationLifecycle,
    ScanCandidate,
    Stock,
)
from app.opportunity_ranking import rank_positive_opportunities
from app.outcomes import evaluate_recommendation
from app.positive_recommendation_gate import evaluate_positive_gate
from app.prediction_trust_score import PREDICTION_TRUST_SCORE_VERSION
from app.recommendation_revision import REASON_MATERIAL_EVIDENCE_CHANGE, create_recommendation_revision

from api.deps import get_db
from app.main import app

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
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


def _make_stock(session, symbol="AAA", sector="TECH"):
    stock = Stock(symbol=symbol, exchange="NSE", sector=sector, company_name=f"{symbol} Ltd", market_cap=Decimal("50000"), is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _make_prediction(session, stock, *, as_of=AS_OF, target_return=Decimal("0.05"), confidence=Decimal("0.80")):
    scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=confidence, sma20_distance=Decimal("0.03"),
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
    return prediction, generation, scan


def _add_evidence_quality(session, prediction, state=STATE_SUFFICIENT):
    session.add(EvidenceQualityDecision(
        prediction_id=prediction.id, state=state, available_category_count=2, stale_category_count=0,
        unavailable_category_count=3, categories_considered=["TECHNICAL_VOLUME", "NEWS"], leaked_categories=[],
        reasons=[], confidence_adjustment_ceiling=prediction.confidence, blocks_publication=(state != STATE_SUFFICIENT),
        evaluated_at=AS_OF, gate_rule_version=EVIDENCE_QUALITY_GATE_VERSION,
    ))
    session.commit()


def _add_trust_score(session, prediction, score=Decimal("0.9")):
    session.add(PredictionTrustScore(
        prediction_id=prediction.id, overall_trust_score=score, trust_quality=QUALITY_HIGH,
        calibration_component=None, historical_accuracy_component=None, recent_performance_component=None,
        horizon_reliability_component=None, regime_reliability_component=None, evidence_quality_component=None,
        available_component_count=1, reasons=[], computed_at=AS_OF, trust_score_version=PREDICTION_TRUST_SCORE_VERSION,
    ))
    session.commit()


def _add_lifecycle(session, generation, state=STATE_ISSUED):
    lifecycle = RecommendationLifecycle(
        recommendation_generation_id=generation.id, state=state, lifecycle_rule_version=LIFECYCLE_VERSION, check_count=0,
    )
    session.add(lifecycle)
    session.commit()
    return lifecycle


def _make_live_recommendation(session, *, symbol="AAA", sector="TECH", target_return=Decimal("0.05")):
    stock = _make_stock(session, symbol=symbol, sector=sector)
    prediction, generation, scan = _make_prediction(session, stock, target_return=target_return)
    _add_evidence_quality(session, prediction)
    _add_trust_score(session, prediction)
    evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)
    rank_positive_opportunities(session, [prediction.id], evaluated_at=AS_OF)
    _add_lifecycle(session, generation)
    return prediction, generation, stock, scan


def test_detail_not_found_returns_canonical_404(client):
    response = client.get("/api/v1/recommendations/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MRA_NOT_FOUND"


def test_detail_returns_full_field_shape(client, session):
    prediction, generation, stock, scan = _make_live_recommendation(session)

    response = client.get(f"/api/v1/recommendations/{generation.id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == generation.id
    assert data["symbol"] == "AAA"
    assert data["status"] == STATE_ISSUED
    assert data["evidenceStrength"] == STATE_SUFFICIENT
    assert data["trustScore"] == "0.90000000"
    assert data["liquidity"] == "NORMAL"  # volume_ratio_20d=1.10 -> NORMAL bucket
    assert data["benchmarkRelative"] is None  # M1.129 not implemented -- honest gap
    assert data["providerEvidence"] == []  # no RecommendationDecisionTrace captured in this test
    assert Decimal(data["targetPrice"]) > Decimal(data["entryPrice"])


def test_detail_reflects_active_revision_not_original(client, session):
    prediction, generation, stock, scan = _make_live_recommendation(session, target_return=Decimal("0.05"))
    revised, _revised_generation, _scan2 = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1), target_return=Decimal("0.10"))
    create_recommendation_revision(
        session, original_prediction=prediction, previous_prediction=prediction, revised_prediction=revised,
        revision_reason=REASON_MATERIAL_EVIDENCE_CHANGE, revised_at=AS_OF + timedelta(days=1),
    )

    response = client.get(f"/api/v1/recommendations/{generation.id}")
    data = response.json()["data"]
    # revised prediction's target_return=0.10 on entry_price=100 -> target 110
    assert Decimal(data["targetPrice"]) == Decimal("110.000000")


def test_history_lists_revisions_with_change_summary(client, session):
    prediction, generation, stock, scan = _make_live_recommendation(session, target_return=Decimal("0.05"))
    revised, _rg, _scan2 = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=1), target_return=Decimal("0.10"))
    create_recommendation_revision(
        session, original_prediction=prediction, previous_prediction=prediction, revised_prediction=revised,
        revision_reason=REASON_MATERIAL_EVIDENCE_CHANGE, revised_at=AS_OF + timedelta(days=1),
    )

    response = client.get(f"/api/v1/recommendations/{generation.id}/history")
    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["version"] == 2
    assert items[0]["triggerType"] == REASON_MATERIAL_EVIDENCE_CHANGE
    assert "target" in items[0]["changeSummary"]


def test_history_empty_when_never_revised(client, session):
    prediction, generation, stock, scan = _make_live_recommendation(session)
    response = client.get(f"/api/v1/recommendations/{generation.id}/history")
    assert response.json()["data"] == []
    assert response.json()["meta"]["nextCursor"] is None


def test_history_date_filter_excludes_out_of_range_revisions(client, session):
    prediction, generation, stock, scan = _make_live_recommendation(session)
    revised, _rg, _scan2 = _make_prediction(session, stock, as_of=AS_OF + timedelta(days=10))
    create_recommendation_revision(
        session, original_prediction=prediction, previous_prediction=prediction, revised_prediction=revised,
        revision_reason=REASON_MATERIAL_EVIDENCE_CHANGE, revised_at=AS_OF + timedelta(days=10),
    )

    response = client.get(f"/api/v1/recommendations/{generation.id}/history", params={"to": (AS_OF + timedelta(days=5)).isoformat()})
    assert response.json()["data"] == []

    response = client.get(f"/api/v1/recommendations/{generation.id}/history", params={"from": (AS_OF + timedelta(days=5)).isoformat()})
    assert len(response.json()["data"]) == 1


def test_events_merges_news_and_corporate_actions_sorted_desc(client, session):
    prediction, generation, stock, scan = _make_live_recommendation(session)
    session.add(NewsEventRecord(
        stock_id=stock.id, source="test", external_id="n1", headline="Older news", event_type="GENERAL",
        materiality="LOW", published_at=AS_OF - timedelta(days=2), fetched_at=AS_OF, ingestion_rule_version="NEV-001",
    ))
    session.add(CorporateAction(
        stock_id=stock.id, action_type="DIVIDEND", effective_date=(AS_OF - timedelta(days=1)).date(),
        ratio=None, cash_amount=Decimal("2.5"), old_symbol=None, new_symbol=None,
        source="test", action_version="CA-001", recorded_at=AS_OF - timedelta(days=1),
    ))
    session.commit()

    response = client.get(f"/api/v1/recommendations/{generation.id}/events")
    items = response.json()["data"]
    assert [item["eventType"] for item in items] == ["CORPORATE_ACTION", "NEWS"]


def test_events_includes_reanalysis_triggers(client, session):
    prediction, generation, stock, scan = _make_live_recommendation(session)
    session.add(EvidenceRevalidationCheck(
        prediction_id=prediction.id, recommendation_evidence_item_id=1, evidence_category="NEWS_EVENT",
        horizon_days=5, freshness_threshold_seconds=3600, revalidation_required=True, reason="STALE_BEYOND_THRESHOLD",
        original_value="v1", current_value="v2", checked_at=AS_OF, revalidation_rule_version="ERC-001",
    ))
    session.commit()

    response = client.get(f"/api/v1/recommendations/{generation.id}/events")
    items = response.json()["data"]
    assert any(item["eventType"] == "REANALYSIS_TRIGGER" for item in items)


def test_events_pagination_covers_every_item_once(client, session):
    prediction, generation, stock, scan = _make_live_recommendation(session)
    for i in range(5):
        session.add(NewsEventRecord(
            stock_id=stock.id, source="test", external_id=f"n{i}", headline=f"Headline {i}", event_type="GENERAL",
            materiality="LOW", published_at=AS_OF - timedelta(days=i), fetched_at=AS_OF, ingestion_rule_version="NEV-001",
        ))
    session.commit()

    seen = []
    cursor = None
    for _ in range(10):
        params = {"pageSize": 2}
        if cursor:
            params["cursor"] = cursor
        body = client.get(f"/api/v1/recommendations/{generation.id}/events", params=params).json()
        seen.extend(item["description"] for item in body["data"])
        cursor = body["meta"]["nextCursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


def test_outcome_is_pending_before_evaluation(client, session):
    prediction, generation, stock, scan = _make_live_recommendation(session)
    response = client.get(f"/api/v1/recommendations/{generation.id}/outcome")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PENDING"
    assert response.json()["data"]["evidenceId"] is None


def test_outcome_reflects_real_evaluated_result(client, session):
    prediction, generation, stock, scan = _make_live_recommendation(session, target_return=Decimal("0.05"))
    horizon_days = prediction.horizon_days
    # Flat trading days up to the horizon, then a target-hit day on the
    # final one -- `evaluate_recommendation` only looks at exactly
    # `horizon_days` subsequent rows, and horizon selection (M1.9/M1.10)
    # decides the actual value, not this test.
    for day in range(1, horizon_days):
        session.add(MarketPrice(
            stock_id=stock.id, timestamp=AS_OF + timedelta(days=day),
            open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"),
            volume=1000, source="test",
        ))
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=horizon_days),
        open=Decimal("100"), high=Decimal("106"), low=Decimal("99"), close=Decimal("105"),
        volume=1000, source="test",
    ))
    session.commit()
    outcome = evaluate_recommendation(session, prediction)
    session.commit()
    assert outcome is not None

    response = client.get(f"/api/v1/recommendations/{generation.id}/outcome")
    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    assert data["targetHit"] is True
    assert data["evidenceId"] == outcome.id
