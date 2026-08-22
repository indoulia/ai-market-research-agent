"""Unit tests for app/upstox_oauth.py (EPIC-MARKSY-0001)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import UpstoxOAuthToken
from app.settings import settings
from app.upstox_oauth import (
    STATE_TTL_SECONDS,
    UpstoxNotConfiguredError,
    UpstoxOAuthError,
    build_authorization_url,
    consume_oauth_state,
    create_oauth_state,
    exchange_authorization_code,
    get_latest_token,
    is_token_valid,
    require_oauth_config,
    resolve_access_token,
    store_token,
)

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


@pytest.fixture(autouse=True)
def _reset_upstox_settings(monkeypatch):
    monkeypatch.setattr(settings, "upstox_client_id", None)
    monkeypatch.setattr(settings, "upstox_client_secret", None)
    monkeypatch.setattr(settings, "upstox_redirect_uri", None)
    monkeypatch.setattr(settings, "upstox_access_token", None)


def test_require_oauth_config_raises_when_missing():
    with pytest.raises(UpstoxNotConfiguredError, match="UPSTOX_CLIENT_ID"):
        require_oauth_config()


def test_require_oauth_config_returns_values_when_set(monkeypatch):
    monkeypatch.setattr(settings, "upstox_client_id", "cid")
    monkeypatch.setattr(settings, "upstox_client_secret", "secret")
    monkeypatch.setattr(settings, "upstox_redirect_uri", "http://localhost:8000/api/v1/integrations/upstox/callback")
    assert require_oauth_config() == ("cid", "secret", "http://localhost:8000/api/v1/integrations/upstox/callback")


def test_build_authorization_url_includes_state_and_redirect():
    url = build_authorization_url(client_id="cid", redirect_uri="http://localhost:8000/cb", state="abc123")
    assert url.startswith("https://api.upstox.com/v2/login/authorization/dialog?")
    assert "client_id=cid" in url
    assert "state=abc123" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fcb" in url


def test_oauth_state_is_single_use(session):
    oauth_state = create_oauth_state(session, issued_at=AS_OF)
    assert consume_oauth_state(session, oauth_state.state, at=AS_OF) is True
    assert consume_oauth_state(session, oauth_state.state, at=AS_OF) is False


def test_oauth_state_rejects_unknown_or_expired(session):
    assert consume_oauth_state(session, "never-issued", at=AS_OF) is False
    oauth_state = create_oauth_state(session, issued_at=AS_OF)
    after_ttl = AS_OF + timedelta(seconds=STATE_TTL_SECONDS + 1)
    assert consume_oauth_state(session, oauth_state.state, at=after_ttl) is False


def test_exchange_authorization_code_success(monkeypatch):
    def fake_post(url, *, data, headers, timeout):
        assert data["grant_type"] == "authorization_code"
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"access_token": "tok-1", "token_type": "Bearer"})

    monkeypatch.setattr(httpx, "post", fake_post)
    payload = exchange_authorization_code("code-1", client_id="cid", client_secret="secret", redirect_uri="http://x")
    assert payload["access_token"] == "tok-1"


def test_exchange_authorization_code_rejects_provider_error(monkeypatch):
    def fake_post(url, *, data, headers, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(400, request=request, json={"error": "invalid_grant"})

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(UpstoxOAuthError):
        exchange_authorization_code("bad-code", client_id="cid", client_secret="secret", redirect_uri="http://x")


def test_exchange_authorization_code_rejects_missing_access_token(monkeypatch):
    def fake_post(url, *, data, headers, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"token_type": "Bearer"})

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(UpstoxOAuthError, match="access_token"):
        exchange_authorization_code("code-1", client_id="cid", client_secret="secret", redirect_uri="http://x")


def _aware(value):
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def test_store_token_defaults_expiry_to_daily_cutover_when_no_expires_in(session):
    token = store_token(session, {"access_token": "tok-1"}, obtained_at=AS_OF)
    assert _aware(token.expires_at) > AS_OF
    assert is_token_valid(token, at=AS_OF) is True


def test_store_token_uses_expires_in_when_provided(session):
    token = store_token(session, {"access_token": "tok-1", "expires_in": 60}, obtained_at=AS_OF)
    assert _aware(token.expires_at) == AS_OF + timedelta(seconds=60)


def test_resolve_access_token_prefers_valid_oauth_token_over_static_env(session, monkeypatch):
    monkeypatch.setattr(settings, "upstox_access_token", "static-token")
    store_token(session, {"access_token": "oauth-token", "expires_in": 3600}, obtained_at=AS_OF)
    assert resolve_access_token(session, at=AS_OF) == "oauth-token"


def test_resolve_access_token_falls_back_to_static_env_when_oauth_token_expired(session, monkeypatch):
    monkeypatch.setattr(settings, "upstox_access_token", "static-token")
    store_token(session, {"access_token": "oauth-token", "expires_in": 60}, obtained_at=AS_OF)
    assert resolve_access_token(session, at=AS_OF + timedelta(seconds=120)) == "static-token"


def test_resolve_access_token_none_when_nothing_configured(session):
    assert resolve_access_token(session, at=AS_OF) is None


def test_get_latest_token_ignores_revoked(session):
    token = store_token(session, {"access_token": "tok-1", "expires_in": 3600}, obtained_at=AS_OF)
    token.revoked_at = AS_OF
    session.add(token)
    session.commit()
    assert get_latest_token(session) is None
