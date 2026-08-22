"""Contract tests for GET /api/v1/performance/* (EPIC-M3.7).

EPIC-M3.7's API Contract explicitly names `/performance/summary`,
`/performance/timeseries` and `/performance/breakdown` as their own
paths. These are thin aliases onto EPIC-M1.147's already-tested
`/tracking/*` service layer (`api/routers/performance.py`) -- these
tests confirm the alias wiring, not the metric math itself (already
covered by `tests/test_api_tracking.py`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcomes import evaluate_recommendation

from api.deps import get_db
from app.main import app

MODEL_VERSION = "test-model-1"
_scan_counter = iter(range(200000, 300000))


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


def _make_prediction(session, *, symbol, as_of, sector="TECH"):
    scan = DailyCandidateScan(scan_date=as_of.date() + timedelta(days=next(_scan_counter)), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", sector=sector, market_cap=Decimal("50000"), is_active=True)
    session.add(stock)
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
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    return prediction, generation, stock


def _close_with_target_hit(session, prediction, stock, *, as_of):
    horizon_days = prediction.horizon_days
    for day in range(1, horizon_days):
        session.add(MarketPrice(
            stock_id=stock.id, timestamp=as_of + timedelta(days=day),
            open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"), volume=1000, source="test",
        ))
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=as_of + timedelta(days=horizon_days),
        open=Decimal("100"), high=Decimal("106"), low=Decimal("99"), close=Decimal("105"), volume=1000, source="test",
    ))
    session.commit()
    outcome = evaluate_recommendation(session, prediction)
    session.commit()
    return outcome


def test_performance_summary_matches_tracking_summary(client, session):
    now = datetime.now(timezone.utc)
    prediction, _generation, stock = _make_prediction(session, symbol="AAA", as_of=now - timedelta(days=1))
    _close_with_target_hit(session, prediction, stock, as_of=now - timedelta(days=1))

    tracking_response = client.get("/api/v1/tracking/summary", params={"range": "30d"})
    performance_response = client.get("/api/v1/performance/summary", params={"range": "30d"})
    assert performance_response.status_code == 200
    assert performance_response.json()["data"] == tracking_response.json()["data"]


def test_performance_summary_invalid_range_rejected(client):
    response = client.get("/api/v1/performance/summary", params={"range": "bogus"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_performance_timeseries_matches_tracking_timeseries(client, session):
    now = datetime.now(timezone.utc)
    prediction, _generation, stock = _make_prediction(session, symbol="AAA", as_of=now - timedelta(days=2))
    _close_with_target_hit(session, prediction, stock, as_of=now - timedelta(days=2))

    tracking_response = client.get("/api/v1/tracking/timeseries", params={"metric": "hitRate", "range": "7d", "bucket": "day"})
    performance_response = client.get("/api/v1/performance/timeseries", params={"metric": "hitRate", "range": "7d", "bucket": "day"})
    assert performance_response.status_code == 200
    # bucketStart is computed relative to `now` at request time, so the two
    # separate calls' bucket boundaries can differ by microseconds -- compare
    # everything except that field (the alias wiring, not the bucketing math,
    # which is already covered by test_api_tracking.py).
    tracking_data = tracking_response.json()["data"]
    performance_data = performance_response.json()["data"]
    assert performance_data["metric"] == tracking_data["metric"]
    assert performance_data["range"] == tracking_data["range"]
    assert performance_data["bucket"] == tracking_data["bucket"]
    assert [(p["value"], p["sampleCount"]) for p in performance_data["points"]] == [
        (p["value"], p["sampleCount"]) for p in tracking_data["points"]
    ]


def test_performance_breakdown_matches_tracking_breakdown(client, session):
    now = datetime.now(timezone.utc)
    prediction, _generation, stock = _make_prediction(session, symbol="AAA", as_of=now - timedelta(days=1))
    _close_with_target_hit(session, prediction, stock, as_of=now - timedelta(days=1))

    tracking_response = client.get("/api/v1/tracking/breakdown", params={"dimension": "horizon"})
    performance_response = client.get("/api/v1/performance/breakdown", params={"dimension": "horizon"})
    assert performance_response.status_code == 200
    assert performance_response.json()["data"] == tracking_response.json()["data"]


def test_performance_breakdown_invalid_dimension_rejected(client):
    response = client.get("/api/v1/performance/breakdown", params={"dimension": "bogus"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_breakdown_by_stock_dimension(client, session):
    """EPIC-M3.7 UI Scope explicitly adds "stock" to the breakdown
    dimensions beyond EPIC-M1.147's original horizon/sector/marketCap/
    regime/setup set."""
    now = datetime.now(timezone.utc)
    prediction, _generation, stock = _make_prediction(session, symbol="AAA", as_of=now - timedelta(days=1))
    _close_with_target_hit(session, prediction, stock, as_of=now - timedelta(days=1))

    for path in ("/api/v1/performance/breakdown", "/api/v1/tracking/breakdown"):
        response = client.get(path, params={"dimension": "stock"})
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["key"] == "AAA"
        assert items[0]["closedCount"] == 1


def test_performance_summary_symbol_filter_matches_tracking(client, session):
    """EPIC-M3.15: the `from`/`to`/`horizon`/`sector`/`marketCap`/`regime`/
    `symbol`/`setup` filter surface this EPIC's API Contract names works
    identically through the `/performance/*` alias as through `/tracking/*`
    -- same underlying `make_filters`/service call, so no logic to
    duplicate-test, just the alias wiring."""
    now = datetime.now(timezone.utc)
    _make_prediction(session, symbol="AAA", as_of=now - timedelta(days=1))
    _make_prediction(session, symbol="BBB", as_of=now - timedelta(days=1))

    tracking_response = client.get("/api/v1/tracking/summary", params={"range": "30d", "symbol": "AAA"})
    performance_response = client.get("/api/v1/performance/summary", params={"range": "30d", "symbol": "AAA"})
    assert performance_response.status_code == 200
    assert performance_response.json()["data"] == tracking_response.json()["data"]
    assert performance_response.json()["data"]["predictionCount"] == 1
