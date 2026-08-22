"""Contract tests for GET /api/v1/system/{health,providers,data-freshness,
events} (EPIC-M3.11)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.discovery_effectiveness import VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK
from app.information_latency import DEGRADATION_RULE_VERSION, VERDICT_DEGRADED
from app.models import LatencyDegradationReport, MarketUnexpectedClosure
from app.provider_outage_tracker import SEVERITY_NONE, SEVERITY_PARTIAL, SEVERITY_TOTAL, record_outage_snapshot
from app.provider_quality import compute_provider_quality_report
from app.refresh_policy import DATA_TYPE_FUNDAMENTAL, DATA_TYPE_MARKET, DATA_TYPE_NEWS_EVENT, FRESHNESS_POLICY, record_fetch_attempt
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

from api.deps import get_db
from api.rate_limit import default_limiter
from app.main import app

AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)  # a Friday


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    default_limiter._hits.clear()
    yield
    default_limiter._hits.clear()


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


def _record_attempts(session, *, data_type, provider_id, count, success, as_of=AS_OF):
    outcome = "ok" if success else "fail"
    for i in range(count):
        record_fetch_attempt(
            session, data_type=data_type, scope_key=f"{provider_id}-{outcome}-{i}", requested_at=as_of,
            source_timestamp=as_of - timedelta(minutes=5), success=success, provider_id=provider_id,
        )


def test_health_reports_ok_on_an_empty_platform(client):
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "OK"
    assert data["databaseOk"] is True
    assert data["providerStatusCounts"] == {}
    assert data["activeOutageCount"] == 0
    assert data["marketSession"] in {"PRE_MARKET", "MARKET_HOURS", "POST_MARKET", "CLOSED"}
    assert data["apiVersion"] == "v1"


def test_providers_endpoint_reports_reliable_provider_as_ok(client, session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _record_attempts(session, data_type=DATA_TYPE_FUNDAMENTAL, provider_id="alpha-vantage", count=total, success=True)

    response = client.get("/api/v1/system/providers")
    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) == 1
    item = items[0]
    assert item["providerId"] == "alpha-vantage"
    assert item["capability"] == DATA_TYPE_FUNDAMENTAL
    assert item["status"] == VERDICT_OK
    assert item["lastSuccessAt"] is not None
    assert item["latencyMs"] == 5 * 60 * 1000
    assert item["failureRate"] == "0"
    assert item["fallbackActive"] is False
    assert item["qualityScore"] == "1"
    assert item["freshness"]["thresholdSeconds"] == int(FRESHNESS_POLICY[DATA_TYPE_FUNDAMENTAL].total_seconds())


def test_providers_endpoint_marks_unreliable_provider_weak_and_fallback_active(client, session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    failing = int(total * 0.5)
    _record_attempts(session, data_type=DATA_TYPE_MARKET, provider_id="yahoo-finance", count=total - failing, success=True)
    _record_attempts(session, data_type=DATA_TYPE_MARKET, provider_id="yahoo-finance", count=failing, success=False)

    report = compute_provider_quality_report(session, computed_at=AS_OF)
    record_outage_snapshot(
        session, data_type=DATA_TYPE_MARKET, registered_provider_ids=("yahoo-finance",),
        quality_report=report, evaluated_at=AS_OF,
    )

    response = client.get("/api/v1/system/providers")
    items = response.json()["data"]
    item = next(i for i in items if i["providerId"] == "yahoo-finance")
    assert item["status"] == VERDICT_WEAK
    assert item["fallbackActive"] is True


def test_providers_endpoint_latency_reflects_most_recent_fetch_not_backfill_average(client, session):
    # Bug found during live Rancher/k3s deployment validation: an 8-month
    # historical candle backfill (source_timestamp spread over months, all
    # requested_at ~= now) plus one genuinely-recent fetch was producing a
    # ~44-hour averaged latencyMs, because latency was averaged across every
    # DataFetchAttempt row ever recorded instead of reflecting the most
    # recent successful fetch (the same row lastSuccessAt is derived from).
    backfill_requested_at = AS_OF
    for months_back in range(1, 9):
        record_fetch_attempt(
            session, data_type=DATA_TYPE_MARKET, scope_key=f"yahoo-finance-backfill-{months_back}",
            requested_at=backfill_requested_at, source_timestamp=backfill_requested_at - timedelta(days=30 * months_back),
            success=True, provider_id="yahoo-finance",
        )

    recent_requested_at = AS_OF + timedelta(days=1)
    recent_lag = timedelta(minutes=5)
    record_fetch_attempt(
        session, data_type=DATA_TYPE_MARKET, scope_key="yahoo-finance-recent",
        requested_at=recent_requested_at, source_timestamp=recent_requested_at - recent_lag,
        success=True, provider_id="yahoo-finance",
    )

    response = client.get("/api/v1/system/providers")
    assert response.status_code == 200
    item = next(i for i in response.json()["data"] if i["providerId"] == "yahoo-finance")

    assert item["latencyMs"] == int(recent_lag.total_seconds() * 1000)
    assert item["latencyMs"] is not None and item["latencyMs"] < 60 * 60 * 1000  # sanity: nowhere near backfill-skewed hours


def test_providers_endpoint_marks_small_sample_insufficient(client, session):
    _record_attempts(session, data_type=DATA_TYPE_NEWS_EVENT, provider_id="finnhub", count=1, success=True)

    response = client.get("/api/v1/system/providers")
    item = response.json()["data"][0]
    assert item["status"] == VERDICT_INSUFFICIENT_SAMPLE


def test_data_freshness_endpoint_reports_per_capability(client, session):
    _record_attempts(session, data_type=DATA_TYPE_MARKET, provider_id="yahoo-finance", count=1, success=True)

    response = client.get("/api/v1/system/data-freshness")
    assert response.status_code == 200
    items = {item["capability"]: item for item in response.json()["data"]}
    assert set(items) == {DATA_TYPE_MARKET, DATA_TYPE_NEWS_EVENT, DATA_TYPE_FUNDAMENTAL}
    assert items[DATA_TYPE_MARKET]["lastSuccessAt"] is not None
    assert items[DATA_TYPE_MARKET]["isFresh"] is True
    assert items[DATA_TYPE_NEWS_EVENT]["lastSuccessAt"] is None
    assert items[DATA_TYPE_NEWS_EVENT]["isFresh"] is False


def test_health_status_is_degraded_when_a_provider_is_weak(client, session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _record_attempts(session, data_type=DATA_TYPE_MARKET, provider_id="yahoo-finance", count=int(total * 0.5), success=True)
    _record_attempts(session, data_type=DATA_TYPE_MARKET, provider_id="yahoo-finance", count=int(total * 0.5), success=False)

    response = client.get("/api/v1/system/health")
    data = response.json()["data"]
    assert data["status"] == "DEGRADED"
    assert data["providerStatusCounts"] == {VERDICT_WEAK: 1}


def test_health_status_is_outage_when_every_provider_for_a_capability_is_degraded(client, session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _record_attempts(session, data_type=DATA_TYPE_MARKET, provider_id="yahoo-finance", count=int(total * 0.5), success=True)
    _record_attempts(session, data_type=DATA_TYPE_MARKET, provider_id="yahoo-finance", count=int(total * 0.5), success=False)

    report = compute_provider_quality_report(session, computed_at=AS_OF)
    record_outage_snapshot(
        session, data_type=DATA_TYPE_MARKET, registered_provider_ids=("yahoo-finance",),
        quality_report=report, evaluated_at=AS_OF,
    )

    response = client.get("/api/v1/system/health")
    data = response.json()["data"]
    assert data["status"] == "OUTAGE"
    assert data["activeOutageCount"] == 1


def test_events_endpoint_merges_and_paginates_incident_history(client, session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _record_attempts(session, data_type=DATA_TYPE_MARKET, provider_id="yahoo-finance", count=int(total * 0.5), success=True)
    _record_attempts(session, data_type=DATA_TYPE_MARKET, provider_id="yahoo-finance", count=int(total * 0.5), success=False)

    report = compute_provider_quality_report(session, computed_at=AS_OF)
    record_outage_snapshot(
        session, data_type=DATA_TYPE_MARKET, registered_provider_ids=("yahoo-finance",),
        quality_report=report, evaluated_at=AS_OF,
    )
    session.add(MarketUnexpectedClosure(
        exchange="NSE", closure_date=date(2027, 1, 2), reason="Unscheduled outage", source="MANUAL_OVERRIDE",
        recorded_at=AS_OF + timedelta(hours=1),
    ))
    session.add(LatencyDegradationReport(
        data_type=DATA_TYPE_FUNDAMENTAL, window_label="7d", sample_count=30, average_latency_seconds=500,
        baseline_sample_count=30, baseline_average_latency_seconds=100, degradation_ratio=4,
        verdict=VERDICT_DEGRADED, computed_at=AS_OF + timedelta(hours=2), report_rule_version=DEGRADATION_RULE_VERSION,
    ))
    session.commit()

    response = client.get("/api/v1/system/events", params={"pageSize": 2})
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    # newest first
    assert body["data"][0]["type"] == "LATENCY_DEGRADATION"
    assert body["data"][1]["type"] == "MARKET_UNEXPECTED_CLOSURE"
    assert body["meta"]["nextCursor"] is not None

    next_page = client.get("/api/v1/system/events", params={"pageSize": 2, "cursor": body["meta"]["nextCursor"]})
    next_body = next_page.json()
    assert len(next_body["data"]) == 1
    assert next_body["data"][0]["type"] == "PROVIDER_OUTAGE"
    assert next_body["meta"]["nextCursor"] is None


def test_events_endpoint_excludes_non_degraded_snapshots(client, session):
    report = compute_provider_quality_report(session, computed_at=AS_OF)
    record_outage_snapshot(
        session, data_type=DATA_TYPE_MARKET, registered_provider_ids=(), quality_report=report, evaluated_at=AS_OF,
    )

    response = client.get("/api/v1/system/events")
    assert response.json()["data"] == []
