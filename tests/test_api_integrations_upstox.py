"""Contract tests for /api/v1/integrations/upstox/{authorize,callback,status}
(EPIC-MARKSY-0001)."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.settings import settings

from api.deps import get_db
from app.main import app

AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)


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


@pytest.fixture(autouse=True)
def _reset_upstox_settings(monkeypatch):
    monkeypatch.setattr(settings, "upstox_client_id", None)
    monkeypatch.setattr(settings, "upstox_client_secret", None)
    monkeypatch.setattr(settings, "upstox_redirect_uri", None)


def _bearer(client, user_id="user-1"):
    token = client.post("/api/v1/auth/login", json={"userId": user_id}).json()["data"]["sessionToken"]
    return {"Authorization": f"Bearer {token}"}


def test_authorize_requires_session(client):
    response = client.get("/api/v1/integrations/upstox/authorize")
    assert response.status_code == 401


def test_authorize_returns_not_configured_when_missing_config(client):
    headers = _bearer(client)
    response = client.get("/api/v1/integrations/upstox/authorize", headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MRA_UPSTOX_NOT_CONFIGURED"


def test_authorize_returns_authorization_url_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "upstox_client_id", "cid")
    monkeypatch.setattr(settings, "upstox_client_secret", "secret")
    monkeypatch.setattr(settings, "upstox_redirect_uri", "http://localhost:8000/api/v1/integrations/upstox/callback")
    headers = _bearer(client)
    response = client.get("/api/v1/integrations/upstox/authorize", headers=headers)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["authorizationUrl"].startswith("https://api.upstox.com/v2/login/authorization/dialog?")
    assert body["state"]


def test_status_reports_not_connected_when_no_token(client):
    headers = _bearer(client)
    response = client.get("/api/v1/integrations/upstox/status", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"] == {
        "connected": False,
        "isExpired": False,
        "obtainedAt": None,
        "expiresAt": None,
        "environment": settings.upstox_environment,
    }


def test_callback_rejects_missing_state(client):
    response = client.get("/api/v1/integrations/upstox/callback", params={"code": "abc"})
    assert response.status_code == 400
    assert "invalid or has expired" in response.text


def test_callback_rejects_unknown_state(client):
    response = client.get("/api/v1/integrations/upstox/callback", params={"code": "abc", "state": "never-issued"})
    assert response.status_code == 400


def test_callback_surfaces_provider_error_query_param(client):
    response = client.get("/api/v1/integrations/upstox/callback", params={"error": "access_denied"})
    assert response.status_code == 400
    assert "access_denied" in response.text


def test_full_authorize_then_callback_connects(client, monkeypatch):
    monkeypatch.setattr(settings, "upstox_client_id", "cid")
    monkeypatch.setattr(settings, "upstox_client_secret", "secret")
    monkeypatch.setattr(settings, "upstox_redirect_uri", "http://localhost:8000/api/v1/integrations/upstox/callback")
    headers = _bearer(client)

    authorize = client.get("/api/v1/integrations/upstox/authorize", headers=headers).json()["data"]
    state = authorize["state"]

    def fake_post(url, *, data, headers, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"access_token": "tok-1", "token_type": "Bearer", "expires_in": 3600})

    monkeypatch.setattr(httpx, "post", fake_post)

    callback = client.get("/api/v1/integrations/upstox/callback", params={"code": "code-1", "state": state})
    assert callback.status_code == 200
    assert "Upstox connected" in callback.text

    status = client.get("/api/v1/integrations/upstox/status", headers=headers).json()["data"]
    assert status["connected"] is True
    assert status["obtainedAt"] is not None
