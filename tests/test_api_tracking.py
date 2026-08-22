"""Contract tests for GET /api/v1/tracking/* (EPIC-M1.147)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import (
    ConfidenceCalibrationRecord,
    DailyCandidateScan,
    MarketPrice,
    Prediction,
    PredictionTrustScore,
    ScanCandidate,
    Stock,
)
from app.outcomes import evaluate_recommendation
from app.prediction_trust_score import PREDICTION_TRUST_SCORE_VERSION

from api.deps import get_db
from app.main import app

MODEL_VERSION = "test-model-1"
_scan_counter = iter(range(100000))
# Deliberately decoupled from any test's `as_of` value: two `_make_prediction`
# calls in the same test with `as_of` timestamps a few hours apart (e.g.
# `now - timedelta(hours=i)` for a small `i`) can round to *different*
# calendar days via `.date()` depending solely on what time of day the CI
# run happens to execute at (a run starting shortly after 00:00 UTC pushes
# an `as_of` just a few hours earlier back a full day). Combined with the
# monotonically increasing `_scan_counter` offset, two such calls could
# land on the exact same `scan_date`, colliding on
# `uq_scan_date_universe_version` -- reproduced for real once CI happened to
# run close to midnight UTC. Anchoring to a fixed epoch instead of
# `as_of.date()` makes every scan's date depend on nothing but the counter,
# so it is unique regardless of wall-clock time.
_SCAN_DATE_EPOCH = date(2000, 1, 1)


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


def _make_prediction(session, *, symbol, as_of, sector="TECH", market_cap=Decimal("50000"), atr_percent=Decimal("0.035")):
    scan = DailyCandidateScan(scan_date=_SCAN_DATE_EPOCH + timedelta(days=next(_scan_counter)), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", sector=sector, market_cap=market_cap, is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=atr_percent, data_quality_passed=True,
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


def _add_trust_score(session, prediction, *, score, at):
    session.add(PredictionTrustScore(
        prediction_id=prediction.id, overall_trust_score=score, trust_quality="HIGH",
        calibration_component=None, historical_accuracy_component=None, recent_performance_component=None,
        horizon_reliability_component=None, regime_reliability_component=None, evidence_quality_component=None,
        available_component_count=1, reasons=[], computed_at=at, trust_score_version=PREDICTION_TRUST_SCORE_VERSION,
    ))
    session.commit()


def test_summary_empty_state(client):
    response = client.get("/api/v1/tracking/summary", params={"range": "30d"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["predictionCount"] == 0
    assert data["closedCount"] == 0
    assert data["targetHitRate"] is None
    assert data["benchmarkReturn"] is None


def test_summary_invalid_range_rejected(client):
    response = client.get("/api/v1/tracking/summary", params={"range": "bogus"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_summary_counts_closed_predictions_in_range(client, session):
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=5)
    prediction, generation, stock = _make_prediction(session, symbol="AAA", as_of=recent)
    _add_trust_score(session, prediction, score=Decimal("0.9"), at=recent)
    _close_with_target_hit(session, prediction, stock, as_of=recent)

    # Outside the 30d window entirely -- must not be counted.
    old = now - timedelta(days=400)
    old_prediction, _old_gen, old_stock = _make_prediction(session, symbol="BBB", as_of=old)
    _close_with_target_hit(session, old_prediction, old_stock, as_of=old)

    response = client.get("/api/v1/tracking/summary", params={"range": "30d"})
    data = response.json()["data"]
    assert data["predictionCount"] == 1
    assert data["closedCount"] == 1
    assert data["targetHitRate"] == "1.0000000000000000000000000000" or Decimal(data["targetHitRate"]) == Decimal(1)
    assert Decimal(data["trustScore"]) == Decimal("0.9")
    assert data["modelVersion"] == MODEL_VERSION
    # AC: "small samples are flagged rather than presented as authoritative"
    assert data["smallSample"] is True  # 1 closed prediction << MIN_SAMPLE_SIZE_FOR_COMPARISON (20)


def test_timeseries_invalid_metric_rejected(client):
    response = client.get("/api/v1/tracking/timeseries", params={"metric": "bogus", "range": "30d", "bucket": "day"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_timeseries_buckets_predictions_by_day(client, session):
    now = datetime.now(timezone.utc)
    p1, _g1, s1 = _make_prediction(session, symbol="AAA", as_of=now - timedelta(days=2))
    _add_trust_score(session, p1, score=Decimal("0.8"), at=now)
    p2, _g2, s2 = _make_prediction(session, symbol="BBB", as_of=now - timedelta(days=2, hours=1))
    _add_trust_score(session, p2, score=Decimal("0.6"), at=now)

    response = client.get("/api/v1/tracking/timeseries", params={"metric": "trust", "range": "7d", "bucket": "day"})
    assert response.status_code == 200
    points = response.json()["data"]["points"]
    matching = [pt for pt in points if pt["sampleCount"] > 0]
    assert len(matching) == 1
    assert matching[0]["sampleCount"] == 2
    assert Decimal(matching[0]["value"]) == Decimal("0.7")


def test_breakdown_by_horizon(client, session):
    now = datetime.now(timezone.utc)
    p1, _g1, s1 = _make_prediction(session, symbol="AAA", as_of=now - timedelta(days=1))
    _close_with_target_hit(session, p1, s1, as_of=now - timedelta(days=1))

    response = client.get("/api/v1/tracking/breakdown", params={"dimension": "horizon"})
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["key"] == f"{p1.horizon_days}d"
    assert items[0]["closedCount"] == 1


def test_breakdown_setup_dimension_is_honest_single_bucket(client, session):
    now = datetime.now(timezone.utc)
    _make_prediction(session, symbol="AAA", as_of=now)

    response = client.get("/api/v1/tracking/breakdown", params={"dimension": "setup"})
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["key"] == "UNCLASSIFIED"


def test_breakdown_invalid_dimension_rejected(client):
    response = client.get("/api/v1/tracking/breakdown", params={"dimension": "bogus"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_predictions_list_filters_by_status(client, session):
    now = datetime.now(timezone.utc)
    closed_pred, closed_gen, closed_stock = _make_prediction(session, symbol="AAA", as_of=now - timedelta(days=1))
    _close_with_target_hit(session, closed_pred, closed_stock, as_of=now - timedelta(days=1))
    active_pred, active_gen, _active_stock = _make_prediction(session, symbol="BBB", as_of=now)

    closed_response = client.get("/api/v1/tracking/predictions", params={"status": "closed"})
    closed_items = closed_response.json()["data"]
    assert [item["symbol"] for item in closed_items] == ["AAA"]
    assert closed_items[0]["outcome"] == "SUCCESS"

    active_response = client.get("/api/v1/tracking/predictions", params={"status": "active"})
    active_items = active_response.json()["data"]
    assert [item["symbol"] for item in active_items] == ["BBB"]
    assert active_items[0]["realizedReturn"] is None


def test_predictions_list_missing_status_rejected(client):
    response = client.get("/api/v1/tracking/predictions")
    assert response.status_code == 422


def test_predictions_list_pagination_covers_every_item_once(client, session):
    now = datetime.now(timezone.utc)
    for i in range(5):
        _make_prediction(session, symbol=f"S{i}", as_of=now - timedelta(hours=i))

    seen = []
    cursor = None
    for _ in range(10):
        params = {"status": "active", "pageSize": 2}
        if cursor:
            params["cursor"] = cursor
        body = client.get("/api/v1/tracking/predictions", params=params).json()
        seen.extend(item["symbol"] for item in body["data"])
        cursor = body["meta"]["nextCursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


# EPIC-M3.15: from/to/horizon/sector/marketCap/regime/symbol/setup filters,
# named as this EPIC's own API Contract "Query" surface and explicitly
# deferred as a real gap by EPIC-M3.7's Completion Report ("genuinely new
# multi-dimension simultaneous filtering ... would be substantial new
# design surface, not a thin alias gap").


def test_summary_from_to_overrides_range(client, session):
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=5)
    _make_prediction(session, symbol="AAA", as_of=recent)
    # Well outside a 10-day from/to window but would be inside 30d/1y.
    old = now - timedelta(days=20)
    _make_prediction(session, symbol="BBB", as_of=old)

    response = client.get(
        "/api/v1/tracking/summary",
        params={"from": (now - timedelta(days=10)).isoformat(), "to": now.isoformat()},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["predictionCount"] == 1
    assert data["range"] == "custom"


def test_summary_from_without_to_rejected(client):
    response = client.get(
        "/api/v1/tracking/summary",
        params={"from": datetime.now(timezone.utc).isoformat()},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_summary_horizon_filter_narrows_population(client, session):
    now = datetime.now(timezone.utc)
    # atr_percent 0.035 -> 1d horizon, 0.010 -> 5d horizon (app/horizon.py's
    # fixed, documented ATR%-to-horizon step function) -- genuinely distinct
    # horizons, not a mutation of an immutable prediction field.
    p1, _g1, _s1 = _make_prediction(session, symbol="AAA", as_of=now - timedelta(days=1), atr_percent=Decimal("0.035"))
    p2, _g2, _s2 = _make_prediction(session, symbol="BBB", as_of=now - timedelta(days=1), atr_percent=Decimal("0.010"))
    assert p1.horizon_days == 1
    assert p2.horizon_days == 5

    response = client.get("/api/v1/tracking/summary", params={"range": "30d", "horizon": 1})
    data = response.json()["data"]
    assert data["predictionCount"] == 1


def test_summary_invalid_horizon_rejected(client):
    response = client.get("/api/v1/tracking/summary", params={"range": "30d", "horizon": 9})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_summary_sector_and_symbol_filters(client, session):
    now = datetime.now(timezone.utc)
    _make_prediction(session, symbol="AAA", as_of=now - timedelta(days=1), sector="TECH")
    _make_prediction(session, symbol="BBB", as_of=now - timedelta(days=1), sector="ENERGY")

    sector_response = client.get("/api/v1/tracking/summary", params={"range": "30d", "sector": "ENERGY"})
    assert sector_response.json()["data"]["predictionCount"] == 1

    symbol_response = client.get("/api/v1/tracking/summary", params={"range": "30d", "symbol": "AAA"})
    assert symbol_response.json()["data"]["predictionCount"] == 1

    none_response = client.get("/api/v1/tracking/summary", params={"range": "30d", "symbol": "ZZZ"})
    assert none_response.json()["data"]["predictionCount"] == 0


def test_breakdown_market_cap_filter(client, session):
    now = datetime.now(timezone.utc)
    p1, _g1, s1 = _make_prediction(session, symbol="AAA", as_of=now)
    from app.discovery_segmentation import classify_market_cap_bucket
    real_bucket = classify_market_cap_bucket(s1.market_cap)

    matching = client.get(
        "/api/v1/tracking/breakdown", params={"dimension": "sector", "marketCap": real_bucket}
    ).json()["data"]["items"]
    assert sum(item["predictionCount"] for item in matching) == 1

    other_bucket = "LARGE_CAP" if real_bucket != "LARGE_CAP" else "SMALL_CAP"
    empty = client.get(
        "/api/v1/tracking/breakdown", params={"dimension": "sector", "marketCap": other_bucket}
    ).json()["data"]["items"]
    assert empty == []


def test_predictions_list_symbol_and_horizon_filters(client, session):
    now = datetime.now(timezone.utc)
    p1, _g1, _s1 = _make_prediction(session, symbol="AAA", as_of=now, atr_percent=Decimal("0.035"))
    p2, _g2, _s2 = _make_prediction(session, symbol="BBB", as_of=now, atr_percent=Decimal("0.010"))
    assert p1.horizon_days == 1
    assert p2.horizon_days == 5

    by_symbol = client.get(
        "/api/v1/tracking/predictions", params={"status": "active", "symbol": "AAA"}
    ).json()["data"]
    assert [item["symbol"] for item in by_symbol] == ["AAA"]

    by_horizon = client.get(
        "/api/v1/tracking/predictions", params={"status": "active", "horizon": 5}
    ).json()["data"]
    assert [item["symbol"] for item in by_horizon] == ["BBB"]

    none_match = client.get(
        "/api/v1/tracking/predictions", params={"status": "active", "symbol": "ZZZ"}
    ).json()["data"]
    assert none_match == []


def test_breakdown_setup_filter_matches_only_unclassified(client, session):
    now = datetime.now(timezone.utc)
    _make_prediction(session, symbol="AAA", as_of=now)

    matches = client.get(
        "/api/v1/tracking/breakdown", params={"dimension": "setup", "setup": "UNCLASSIFIED"}
    ).json()["data"]["items"]
    assert len(matches) == 1

    none_match = client.get(
        "/api/v1/tracking/breakdown", params={"dimension": "setup", "setup": "BREAKOUT"}
    ).json()["data"]["items"]
    assert none_match == []
