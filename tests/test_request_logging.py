"""Regression tests for the request-path logging added in the 2026-08-21
QA/integration audit (api/request_logging.py, wired via api/middleware.py)."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.deps import get_db
from api.request_logging import logger as request_logger
from app.db import Base
from app.main import app


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


def test_request_logs_operational_fields_only(client, caplog):
    with caplog.at_level(logging.INFO, logger="mra.api.request"):
        response = client.get(
            "/api/v1/recommendations", headers={"Authorization": "Bearer super-secret-token-value"}
        )

    assert response.status_code == 200
    matching = [r for r in caplog.records if r.name == "mra.api.request"]
    assert len(matching) == 1
    fields = matching[0].fields
    assert fields["method"] == "GET"
    assert fields["route"] == "/api/v1/recommendations"
    assert fields["status"] == 200
    assert fields["durationMs"] >= 0
    assert fields["requestId"]
    assert "timestamp" in fields

    logged_text = str(fields)
    assert "super-secret-token-value" not in logged_text
    assert "Authorization" not in logged_text


def test_request_logging_is_idempotent_to_configure_across_multiple_app_instances():
    from api.request_logging import configure_request_logging

    handlers_before = len(request_logger.handlers)
    configure_request_logging()
    configure_request_logging()
    assert len(request_logger.handlers) == handlers_before
