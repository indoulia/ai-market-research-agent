"""Contract tests for GET/PUT /api/v1/preferences and POST
/api/v1/recommendations/{id}/feedback (EPIC-M1.141)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth_session import create_session
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, Prediction, ScanCandidate, Stock

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


def _auth(session, user_id="user-1"):
    # EPIC-M1.145: the bearer token must be a real, live AuthSession now --
    # a self-asserted string is no longer accepted (see api/deps.py::
    # require_active_session).
    auth_session = create_session(session, user_id=user_id, issued_at=AS_OF)
    return {"Authorization": f"Bearer {auth_session.session_token}"}


def _make_recommendation(session, *, symbol="AAA"):
    scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", sector="TECH", is_active=True)
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
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    return prediction, generation


# ---- Preferences ----


def test_preferences_requires_auth(client):
    response = client.get("/api/v1/preferences")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MRA_UNAUTHENTICATED"


def test_preferences_defaults_for_new_user(client, session):
    response = client.get("/api/v1/preferences", headers=_auth(session))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["defaultHorizon"] == 1  # SHORT band's lower bound, never-set default
    assert data["markets"] == []
    assert data["watchlist"] == []
    assert data["notificationPreferences"] == {"mutedAlertTypes": []}
    assert data["riskPreference"] == "MEDIUM"


def test_put_preferences_round_trips(client, session):
    headers = _auth(session)
    body = {
        "defaultHorizon": 5,
        "markets": ["NSE"],
        "sectors": ["TECH", "PHARMA"],
        "industries": ["SOFTWARE"],
        "marketCapBuckets": ["LARGE_CAP"],
        "watchlist": ["AAA", "BBB"],
        "notificationPreferences": {"mutedAlertTypes": ["NEW_OPPORTUNITY"]},
        "displayPreferences": {"theme": "dark"},
        "riskPreference": "HIGH",
    }
    put_response = client.put("/api/v1/preferences", json=body, headers=headers)
    assert put_response.status_code == 200

    get_response = client.get("/api/v1/preferences", headers=headers)
    data = get_response.json()["data"]
    assert data["defaultHorizon"] == 5
    assert data["markets"] == ["NSE"]
    assert data["sectors"] == ["TECH", "PHARMA"]
    assert data["industries"] == ["SOFTWARE"]
    assert data["marketCapBuckets"] == ["LARGE_CAP"]
    assert data["watchlist"] == ["AAA", "BBB"]
    assert data["notificationPreferences"] == {"mutedAlertTypes": ["NEW_OPPORTUNITY"]}
    assert data["displayPreferences"]["theme"] == "dark"
    assert data["riskPreference"] == "HIGH"


def test_put_preferences_invalid_horizon_rejected(client, session):
    body = {"defaultHorizon": 2}  # not in VALID_HORIZON_DAYS (1,3,5,7)
    response = client.put("/api/v1/preferences", json=body, headers=_auth(session))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_preferences_are_isolated_per_user(client, session):
    client.put("/api/v1/preferences", json={"defaultHorizon": 7, "watchlist": ["ZZZ"]}, headers=_auth(session, "user-a"))
    response = client.get("/api/v1/preferences", headers=_auth(session, "user-b"))
    data = response.json()["data"]
    assert data["watchlist"] == []
    assert data["defaultHorizon"] == 1


# ---- Feedback ----


def test_feedback_accepted_useful(client, session):
    prediction, generation = _make_recommendation(session)
    response = client.post(
        f"/api/v1/recommendations/{generation.id}/feedback",
        json={"type": "useful", "comment": "great call", "predictionVersion": prediction.model_version},
        headers=_auth(session),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["accepted"] is True
    assert data["learningImpact"] == "informational"
    assert data["feedbackId"]


def test_feedback_target_type_is_queued_for_learning(client, session):
    prediction, generation = _make_recommendation(session)
    response = client.post(
        f"/api/v1/recommendations/{generation.id}/feedback",
        json={"type": "target_too_high", "predictionVersion": prediction.model_version},
        headers=_auth(session),
    )
    assert response.json()["data"]["learningImpact"] == "queued"


def test_feedback_unknown_type_rejected(client, session):
    prediction, generation = _make_recommendation(session)
    response = client.post(
        f"/api/v1/recommendations/{generation.id}/feedback",
        json={"type": "bogus", "predictionVersion": prediction.model_version},
        headers=_auth(session),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_feedback_stale_prediction_version_rejected(client, session):
    prediction, generation = _make_recommendation(session)
    response = client.post(
        f"/api/v1/recommendations/{generation.id}/feedback",
        json={"type": "useful", "predictionVersion": "some-old-version"},
        headers=_auth(session),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MRA_STALE_PREDICTION_VERSION"


def test_feedback_not_found_recommendation(client, session):
    response = client.post(
        "/api/v1/recommendations/999999/feedback",
        json={"type": "useful", "predictionVersion": "v1"},
        headers=_auth(session),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MRA_NOT_FOUND"


def test_feedback_duplicate_idempotency_key_returns_same_feedback(client, session):
    prediction, generation = _make_recommendation(session)
    headers = {**_auth(session), "Idempotency-Key": "client-req-1"}
    body = {"type": "useful", "predictionVersion": prediction.model_version}

    first = client.post(f"/api/v1/recommendations/{generation.id}/feedback", json=body, headers=headers)
    second = client.post(f"/api/v1/recommendations/{generation.id}/feedback", json=body, headers=headers)

    assert first.json()["data"]["feedbackId"] == second.json()["data"]["feedbackId"]

    from app.recommendation_feedback import get_feedback_for_prediction
    assert len(get_feedback_for_prediction(session, prediction.id)) == 1


def test_feedback_without_idempotency_key_creates_separate_records(client, session):
    prediction, generation = _make_recommendation(session)
    body = {"type": "useful", "predictionVersion": prediction.model_version}

    client.post(f"/api/v1/recommendations/{generation.id}/feedback", json=body, headers=_auth(session))
    client.post(f"/api/v1/recommendations/{generation.id}/feedback", json=body, headers=_auth(session))

    from app.recommendation_feedback import get_feedback_for_prediction
    assert len(get_feedback_for_prediction(session, prediction.id)) == 2
