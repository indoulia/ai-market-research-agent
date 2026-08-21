"""Contract tests for GET /api/v1/predictions/active[/{predictionId}] (EPIC-M3.8)."""

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
    DailyCandidateScan,
    EvidenceQualityDecision,
    MarketPrice,
    Prediction,
    PredictionOutcomeEvent,
    PredictionTrustScore,
    RecommendationEvidenceItem,
    RecommendationGeneration,
    RecommendationLifecycle,
    ScanCandidate,
    Stock,
)
from app.opportunity_ranking import rank_positive_opportunities
from app.positive_recommendation_gate import evaluate_positive_gate
from app.prediction_outcome_monitor import MONITOR_RULE_VERSION, STATE_STOP_LOSS_HIT, STATE_TARGET_HIT
from app.prediction_trust_score import PREDICTION_TRUST_SCORE_VERSION

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


def _make_prediction(session, symbol="AAA", sector="TECH", target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), close=Decimal("100")):
    scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", sector=sector, company_name=f"{symbol} Ltd", market_cap=Decimal("1000000000"), is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF,
        open=close, high=close + 1, low=close - 1, close=close,
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
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=close,
        target_return=target_return, stop_return=stop_return,
    )
    prediction = session.get(Prediction, generation.prediction_id)
    return prediction, generation, stock, scan


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


def _make_gate_passed(session, *, symbol="AAA", sector="TECH", target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), trust_score=Decimal("0.9"), close=Decimal("100")):
    prediction, generation, stock, _scan = _make_prediction(session, symbol=symbol, sector=sector, target_return=target_return, stop_return=stop_return, close=close)
    _add_evidence_quality(session, prediction)
    _add_trust_score(session, prediction, score=trust_score)
    evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)
    return prediction, generation, stock


def _rank_and_activate(session, entries, *, evaluated_at=AS_OF):
    predictions = [prediction for prediction, _generation, _stock in entries]
    rank_positive_opportunities(session, [p.id for p in predictions], evaluated_at=evaluated_at)
    for _prediction, generation, _stock in entries:
        _add_lifecycle(session, generation)
    return entries


def _make_active_prediction(session, **kwargs):
    entry = _make_gate_passed(session, **kwargs)
    _rank_and_activate(session, [entry])
    return entry


def _add_outcome_event(session, prediction, state, evidence=None):
    session.add(PredictionOutcomeEvent(
        prediction_id=prediction.id, state=state, detected_at=AS_OF + timedelta(days=1),
        observed_at=AS_OF + timedelta(days=1), observed_price=Decimal("110"), provider="test",
        prediction_version=f"{MODEL_VERSION}:t", evidence=evidence or {}, monitor_rule_version=MONITOR_RULE_VERSION,
    ))
    session.commit()


def test_empty_when_no_ranking_batch_exists(client):
    response = client.get("/api/v1/predictions/active")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["nextCursor"] is None


def test_returns_active_prediction_with_full_fields(client, session):
    prediction, generation, stock = _make_active_prediction(session)

    response = client.get("/api/v1/predictions/active")
    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) == 1
    item = items[0]
    assert item["predictionId"] == prediction.id
    assert item["symbol"] == "AAA"
    assert item["companyName"] == "AAA Ltd"
    assert item["exchange"] == "NSE"
    assert item["price"] == "100.000000"
    assert Decimal(item["targetPrice"]) > Decimal(item["price"])
    assert Decimal(item["stopLoss"]) < Decimal(item["price"])
    assert item["status"] == "ACTIVE"
    assert item["trustScore"] == "0.90000000"
    assert item["lastRevisionAt"] is None
    assert item["remainingTradingDays"] is not None
    assert item["distanceToTargetPercent"] is not None
    assert item["distanceToStopLossPercent"] is not None
    assert item["lastPriceAt"] is not None


def test_closed_lifecycle_predictions_are_excluded(client, session):
    from app.lifecycle import STATE_EVALUATED

    prediction, generation, stock = _make_active_prediction(session, symbol="AAA")
    lifecycle = session.query(RecommendationLifecycle).filter_by(recommendation_generation_id=generation.id).one()
    lifecycle.state = STATE_EVALUATED
    session.commit()

    response = client.get("/api/v1/predictions/active")
    assert response.json()["data"] == []


def test_status_reflects_m119_terminal_event_not_recomputed(client, session):
    """AC: 'active state is sourced from M1.119, not recomputed differently'."""
    prediction, generation, stock = _make_active_prediction(session, symbol="AAA")
    _add_outcome_event(session, prediction, STATE_TARGET_HIT, evidence={"trigger": "target_price"})

    response = client.get("/api/v1/predictions/active")
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["status"] == STATE_TARGET_HIT
    # Once terminal, there is nothing further to evaluate.
    assert items[0]["nextEvaluationAt"] is None


def test_stop_loss_hit_status(client, session):
    prediction, generation, stock = _make_active_prediction(session, symbol="AAA")
    _add_outcome_event(session, prediction, STATE_STOP_LOSS_HIT)

    response = client.get("/api/v1/predictions/active")
    assert response.json()["data"][0]["status"] == STATE_STOP_LOSS_HIT


def test_distance_calculations_are_price_relative(client, session):
    # entry=100, target_return=0.10 -> target=110; stop_return=-0.05 -> stop=95.
    # Current close is also 100 (== entry), so distances are exactly +10%/+5%.
    prediction, generation, stock = _make_active_prediction(
        session, symbol="AAA", target_return=Decimal("0.10"), stop_return=Decimal("-0.05"), close=Decimal("100")
    )

    response = client.get("/api/v1/predictions/active")
    item = response.json()["data"][0]
    assert Decimal(item["distanceToTargetPercent"]) == Decimal("10.000000000000")
    assert Decimal(item["distanceToStopLossPercent"]) == Decimal("5.000000000000")


def test_pagination_covers_every_row_exactly_once(client, session):
    entries = [_make_gate_passed(session, symbol=f"S{i}", sector=f"SECTOR{i}", target_return=Decimal("0.02") + Decimal(i) / 100) for i in range(5)]
    _rank_and_activate(session, entries)

    seen = []
    cursor = None
    for _ in range(10):
        params = {"pageSize": 2}
        if cursor:
            params["cursor"] = cursor
        body = client.get("/api/v1/predictions/active", params=params).json()
        seen.extend(item["symbol"] for item in body["data"])
        cursor = body["meta"]["nextCursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


def test_detail_endpoint_returns_same_prediction(client, session):
    prediction, generation, stock = _make_active_prediction(session, symbol="AAA")

    response = client.get(f"/api/v1/predictions/active/{prediction.id}")
    assert response.status_code == 200
    item = response.json()["data"]
    assert item["predictionId"] == prediction.id
    assert item["symbol"] == "AAA"
    assert item["status"] == "ACTIVE"


def test_detail_endpoint_reflects_target_hit_after_lifecycle_closure(client, session):
    """AC: 'target/SL closure appears consistently after outcome confirmation' --
    the detail view stays correct even once the lifecycle has moved on."""
    from app.lifecycle import STATE_EVALUATED

    prediction, generation, stock = _make_active_prediction(session, symbol="AAA")
    _add_outcome_event(session, prediction, STATE_TARGET_HIT)
    lifecycle = session.query(RecommendationLifecycle).filter_by(recommendation_generation_id=generation.id).one()
    lifecycle.state = STATE_EVALUATED
    session.commit()

    response = client.get(f"/api/v1/predictions/active/{prediction.id}")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == STATE_TARGET_HIT


def test_detail_endpoint_404_for_unknown_prediction(client, session):
    response = client.get("/api/v1/predictions/active/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MRA_NOT_FOUND"


def test_stale_market_price_does_not_crash_when_missing(client, session):
    # A prediction with no MarketPrice row at all (edge case): price/distance
    # fields must be None, never fabricated or a crash.
    prediction, generation, stock, _scan = _make_prediction(session, symbol="NOPRICE")
    session.query(MarketPrice).filter_by(stock_id=stock.id).delete()
    session.commit()
    _add_evidence_quality(session, prediction)
    _add_trust_score(session, prediction)
    evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)
    _rank_and_activate(session, [(prediction, generation, stock)])

    response = client.get("/api/v1/predictions/active")
    item = response.json()["data"][0]
    assert item["price"] is None
    assert item["distanceToTargetPercent"] is None
    assert item["distanceToStopLossPercent"] is None
    assert item["lastPriceAt"] is None
