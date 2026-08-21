"""Contract tests for the /api/v1 foundation (EPIC-M1.132).

Runs entirely against an in-memory sqlite DB (no external services), so it
can run independently of any Flutter client, per the EPIC's acceptance
criteria.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.deps import get_db
from api.errors import NotFoundError, ValidationError
from api.exception_handlers import register_exception_handlers
from api.pagination import PageParams, parse_sort
from api.rate_limit import RateLimiter
from app.db import Base
from app.main import app


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health_envelope_shape(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {"status": "ok", "component": "market-agent-m1", "apiVersion": "v1"}
    assert set(body["meta"]) == {"requestId", "timestamp"}
    assert body["meta"]["requestId"]
    assert response.headers["X-Request-Id"] == body["meta"]["requestId"]


def test_request_id_is_propagated_from_inbound_header(client):
    response = client.get("/api/v1/health", headers={"X-Request-Id": "caller-supplied-id"})
    assert response.headers["X-Request-Id"] == "caller-supplied-id"
    assert response.json()["meta"]["requestId"] == "caller-supplied-id"


def test_bootstrap_reports_contract_and_capabilities(client):
    response = client.get("/api/v1/app/bootstrap")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["apiVersion"] == "v1"
    assert data["contractVersion"]
    assert data["capabilities"] == {
        "recommendations": True,
        "discovery": True,
        "marketSummary": True,
        "news": True,
        "events": True,
        "feedback": True,
        "preferences": True,
        "auth": True,
        "analytics": False,
    }


def test_unmatched_route_returns_canonical_error_envelope(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "MRA_NOT_FOUND"
    assert body["error"]["retryable"] is False
    assert set(body["meta"]) == {"requestId", "timestamp"}


def test_pydantic_validation_error_maps_to_canonical_envelope():
    probe_app = FastAPI()
    register_exception_handlers(probe_app)

    @probe_app.get("/probe")
    def _probe(params: PageParams = Depends()):
        return {"page": params.page}

    response = TestClient(probe_app).get("/probe", params={"pageSize": "not-a-number"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "MRA_VALIDATION_FAILED"
    assert any(key.endswith("pageSize") for key in body["error"]["details"]["fieldErrors"])


def test_legacy_routes_are_untouched(client, monkeypatch):
    # app.main.health() opens its own SessionLocal() directly (it predates
    # api.deps.get_db and isn't part of the /api/v1 contract this EPIC owns),
    # so the `client` fixture's dependency override doesn't reach it. Point
    # the module-level SessionLocal at an in-memory sqlite engine instead of
    # whatever real DATABASE_URL happens to be configured in this environment.
    import app.main as main_module

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main_module, "SessionLocal", sessionmaker(bind=engine))

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "component": "market-agent-m1"}


def test_not_found_error_maps_to_mra_not_found():
    exc = NotFoundError("Recommendation", "123")
    assert exc.code == "MRA_NOT_FOUND"
    assert exc.http_status == 404
    assert exc.details == {"resource": "Recommendation", "identifier": "123"}


def test_validation_error_maps_to_mra_validation_failed():
    exc = ValidationError("bad sort field", field_errors={"sort": "unknown"})
    assert exc.code == "MRA_VALIDATION_FAILED"
    assert exc.http_status == 422


def test_parse_sort_accepts_allowed_fields_with_direction():
    assert parse_sort("-createdAt,symbol", {"createdAt", "symbol"}) == [
        ("createdAt", True),
        ("symbol", False),
    ]


def test_parse_sort_rejects_unknown_field():
    with pytest.raises(ValidationError):
        parse_sort("bogusField", {"createdAt"})


def test_parse_sort_empty_is_no_op():
    assert parse_sort(None, {"createdAt"}) == []


def test_rate_limiter_allows_up_to_limit_then_rejects():
    limiter = RateLimiter(limit=2, window_seconds=60)
    limiter.check("caller-a", now=0.0)
    limiter.check("caller-a", now=1.0)
    with pytest.raises(Exception) as excinfo:
        limiter.check("caller-a", now=2.0)
    assert excinfo.value.code == "MRA_RATE_LIMITED"
    assert excinfo.value.retryable is True


def test_rate_limiter_resets_after_window():
    limiter = RateLimiter(limit=1, window_seconds=10)
    limiter.check("caller-b", now=0.0)
    limiter.check("caller-b", now=11.0)  # new window, should not raise


def test_rate_limiter_evicts_stale_keys_so_memory_does_not_grow_unbounded():
    """Found in the 2026-08-21 QA/integration audit: `_hits` previously kept an
    entry forever for every distinct key ever seen. Once a key's window has
    expired, later `check()` calls for OTHER keys should reclaim it."""
    limiter = RateLimiter(limit=10, window_seconds=60)
    for i in range(500):
        limiter.check(f"caller-{i}", now=0.0)
    assert limiter.tracked_key_count() == 500

    # All 500 windows are now expired; touching one new key should sweep them.
    limiter.check("caller-new", now=1000.0)
    assert limiter.tracked_key_count() == 1


def test_rate_limiter_caps_tracked_keys_even_within_a_single_live_window():
    """Backstop for many distinct keys arriving within one still-live window
    (expiry-based eviction alone can't bound this case)."""
    limiter = RateLimiter(limit=10, window_seconds=60, max_tracked_keys=100)
    for i in range(150):
        limiter.check(f"caller-{i}", now=0.0)
    assert limiter.tracked_key_count() == 100


def test_rate_limiter_eviction_does_not_disturb_an_active_caller_within_the_cap():
    limiter = RateLimiter(limit=5, window_seconds=60, max_tracked_keys=3)
    limiter.check("keep-me", now=0.0)
    limiter.check("keep-me", now=1.0)
    limiter.check("other-1", now=2.0)
    limiter.check("other-2", now=3.0)

    limiter.check("keep-me", now=4.0)  # re-touching moves it to most-recently-used
    limiter.check("other-3", now=5.0)  # pushes the map to 4 entries -> evicts oldest untouched

    assert limiter.tracked_key_count() == 3
    # "keep-me" was touched most recently among the original three, so it survives
    # and its count (3 checks so far) is preserved rather than reset.
    with pytest.raises(Exception):
        for _ in range(3):
            limiter.check("keep-me", now=5.0)
