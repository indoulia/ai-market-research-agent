"""Contract tests for the /api/v1 foundation (EPIC-M1.132).

Runs entirely against an in-memory sqlite DB (no external services), so it
can run independently of any Flutter client, per the EPIC's acceptance
criteria.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.app import register_api
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
        "analytics": True,
        "dashboard": True,
    }


def test_version_endpoint_reports_api_and_contract_version(client):
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["apiVersion"] == "v1"
    assert data["contractVersion"]


def test_capabilities_endpoint_matches_bootstrap_capabilities(client):
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    capabilities = response.json()["data"]
    bootstrap_capabilities = client.get("/api/v1/app/bootstrap").json()["data"]["capabilities"]
    assert capabilities == bootstrap_capabilities
    assert capabilities == {
        "recommendations": True,
        "discovery": True,
        "marketSummary": True,
        "news": True,
        "events": True,
        "feedback": True,
        "preferences": True,
        "auth": True,
        "analytics": True,
        "dashboard": True,
    }


def test_version_and_capabilities_are_cacheable_with_etag(client):
    """EPIC-M3.13 — API Scope: "Cache headers/ETags where safe". Both bodies
    are build-time constants (never DB-derived), so they are exactly the
    "cacheable, slowly-changing data" EPIC-M3.1's own completion report
    named as the missing precondition for adding this."""
    for path in ("/api/v1/version", "/api/v1/capabilities"):
        first = client.get(path)
        assert first.status_code == 200
        assert first.headers["Cache-Control"] == "public, max-age=300"
        etag = first.headers["ETag"]
        assert etag

        cached = client.get(path, headers={"If-None-Match": etag})
        assert cached.status_code == 304
        assert cached.headers["ETag"] == etag
        assert cached.content == b""


def test_every_api_response_carries_server_timing_header(client):
    """EPIC-M3.13 — API Scope: "Server timing/correlation metadata".
    Correlation is X-Request-Id (existing); this is the timing half, a
    standard client-parseable header rather than only a server-side log."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    timing = response.headers["Server-Timing"]
    assert timing.startswith("total;dur=")
    duration = float(timing.removeprefix("total;dur="))
    assert duration >= 0


def test_large_api_responses_are_gzip_compressed(monkeypatch):
    """EPIC-M3.13 — API Scope: "Compression"."""
    probe_app = FastAPI()
    register_api(probe_app)

    @probe_app.get("/api/v1/_probe/large")
    def _probe_large():
        return {"data": "x" * 2000, "meta": {}}

    probe_client = TestClient(probe_app)
    response = probe_client.get(
        "/api/v1/_probe/large", headers={"Accept-Encoding": "gzip"}
    )
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert response.json()["data"] == "x" * 2000


def test_oversized_response_is_logged_for_monitoring(client, monkeypatch, caplog):
    """EPIC-M3.13 — API Scope: "response-size monitoring". A response this
    large for one /api/v1 call should surface in ops logs, not ship
    silently."""
    import api.middleware as middleware

    monkeypatch.setattr(middleware, "LARGE_RESPONSE_BYTES", 10)
    with caplog.at_level(logging.WARNING, logger="api.middleware"):
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert any("Oversized" in record.message for record in caplog.records)


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
