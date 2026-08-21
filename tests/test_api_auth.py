"""Contract tests for /api/v1/auth/login, /api/v1/auth/refresh,
/api/v1/auth/session, /api/v1/auth/logout, /api/v1/me and
/api/v1/me/permissions (EPIC-M1.145, endpoint split to EPIC-M3.12's
login/refresh/session contract)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base

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


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, user_id="user-1"):
    return client.post("/api/v1/auth/login", json={"userId": user_id}).json()["data"]


def test_login_requires_user_id(client):
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_login_rejects_blank_user_id(client):
    response = client.post("/api/v1/auth/login", json={"userId": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MRA_VALIDATION_FAILED"


def test_login_returns_real_token(client):
    response = client.post("/api/v1/auth/login", json={"userId": "user-1"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["userId"] == "user-1"
    assert len(data["sessionToken"]) >= 32
    assert data["expiresAt"] > data["issuedAt"]


def test_login_response_carries_request_id_in_meta(client):
    response = client.post("/api/v1/auth/login", json={"userId": "user-1"})
    assert response.json()["meta"]["requestId"]


def test_me_requires_auth(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MRA_UNAUTHENTICATED"


def test_me_returns_user_context_for_valid_session(client):
    session_data = _login(client)
    response = client.get("/api/v1/me", headers=_bearer(session_data["sessionToken"]))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["userId"] == "user-1"
    assert data["sessionExpiresAt"] == session_data["expiresAt"]
    assert data["requestId"]


def test_me_rejects_unknown_token(client):
    response = client.get("/api/v1/me", headers=_bearer("not-a-real-token"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MRA_UNAUTHENTICATED"


def test_auth_session_requires_auth(client):
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MRA_UNAUTHENTICATED"


def test_auth_session_returns_user_context_for_valid_session(client):
    session_data = _login(client)
    response = client.get("/api/v1/auth/session", headers=_bearer(session_data["sessionToken"]))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["userId"] == "user-1"
    assert data["sessionExpiresAt"] == session_data["expiresAt"]
    assert data["requestId"]


def test_auth_session_rejects_unknown_token(client):
    response = client.get("/api/v1/auth/session", headers=_bearer("not-a-real-token"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MRA_UNAUTHENTICATED"


def test_permissions_returns_default_capabilities(client):
    session_data = _login(client)
    response = client.get("/api/v1/me/permissions", headers=_bearer(session_data["sessionToken"]))
    assert response.status_code == 200
    assert "VIEW_RECOMMENDATIONS" in response.json()["data"]["capabilities"]


def test_logout_revokes_session(client):
    session_data = _login(client)
    token = session_data["sessionToken"]

    logout_response = client.post("/api/v1/auth/logout", headers=_bearer(token))
    assert logout_response.status_code == 200
    assert logout_response.json()["data"]["revoked"] is True

    me_response = client.get("/api/v1/me", headers=_bearer(token))
    assert me_response.status_code == 401
    assert me_response.json()["error"]["code"] == "MRA_UNAUTHENTICATED"


def test_logout_is_idempotent(client):
    session_data = _login(client)
    token = session_data["sessionToken"]

    first = client.post("/api/v1/auth/logout", headers=_bearer(token))
    second = client.post("/api/v1/auth/logout", headers=_bearer(token))
    assert first.json()["data"]["revoked"] is True
    assert second.json()["data"]["revoked"] is False


def test_logout_without_token_is_unauthenticated(client):
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MRA_UNAUTHENTICATED"


def test_refresh_requires_auth(client):
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MRA_UNAUTHENTICATED"


def test_refresh_rejects_unknown_token(client):
    response = client.post("/api/v1/auth/refresh", headers=_bearer("not-a-real-token"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MRA_UNAUTHENTICATED"


def test_refresh_rotates_token_and_invalidates_old_one(client):
    session_data = _login(client)
    old_token = session_data["sessionToken"]

    refresh_response = client.post("/api/v1/auth/refresh", headers=_bearer(old_token))
    assert refresh_response.status_code == 200
    new_data = refresh_response.json()["data"]
    assert new_data["sessionToken"] != old_token
    assert new_data["userId"] == "user-1"

    old_still_works = client.get("/api/v1/me", headers=_bearer(old_token))
    assert old_still_works.status_code == 401

    new_works = client.get("/api/v1/me", headers=_bearer(new_data["sessionToken"]))
    assert new_works.status_code == 200


def test_refresh_after_revoke_is_unauthenticated(client):
    session_data = _login(client)
    token = session_data["sessionToken"]
    client.post("/api/v1/auth/logout", headers=_bearer(token))

    response = client.post("/api/v1/auth/refresh", headers=_bearer(token))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MRA_UNAUTHENTICATED"


def test_refresh_of_expired_session_returns_deterministic_error_code(client, session):
    from app.auth_session import create_session
    from app.models import AuthSession as AuthSessionModel

    auth_session = create_session(session, user_id="user-1", issued_at=AS_OF, ttl_seconds=60)
    row = session.get(AuthSessionModel, auth_session.id)
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()

    response = client.post("/api/v1/auth/refresh", headers=_bearer(auth_session.session_token))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MRA_SESSION_EXPIRED"


def test_expired_session_returns_deterministic_error_code(client, session):
    from app.auth_session import create_session
    from app.models import AuthSession as AuthSessionModel

    auth_session = create_session(session, user_id="user-1", issued_at=AS_OF, ttl_seconds=60)
    session.commit()

    # `require_active_session` compares expires_at against the *real* wall
    # clock (datetime.now()), not this test's fictional AS_OF -- age the
    # session relative to real now, not AS_OF, to actually trip expiry.
    row = session.get(AuthSessionModel, auth_session.id)
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()

    response = client.get("/api/v1/me", headers=_bearer(auth_session.session_token))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MRA_SESSION_EXPIRED"

    session_response = client.get("/api/v1/auth/session", headers=_bearer(auth_session.session_token))
    assert session_response.status_code == 401
    assert session_response.json()["error"]["code"] == "MRA_SESSION_EXPIRED"


def test_recommendations_endpoint_still_requires_no_auth(client):
    # M1.135's list endpoint predates M1.145 and is unauthenticated by
    # contract (versioning policy: adding auth to an existing v1 endpoint
    # would be a breaking change, not an in-place addition).
    response = client.get("/api/v1/recommendations")
    assert response.status_code == 200
