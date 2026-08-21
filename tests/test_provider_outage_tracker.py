from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery_effectiveness import DiscoveryEffectivenessReport
from app.provider_outage_tracker import (
    OUTAGE_SNAPSHOT_VERSION,
    SEVERITY_NONE,
    SEVERITY_PARTIAL,
    SEVERITY_TOTAL,
    get_latest_outage_snapshot,
    get_outage_history,
    record_outage_snapshot,
)
from app.provider_quality import ProviderQualityMetric, ProviderQualityReport

AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
DATA_TYPE = "MARKET_DATA"


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _metric(provider_id, verdict, data_type=DATA_TYPE):
    return ProviderQualityMetric(
        data_type=data_type, provider_id=provider_id, total_attempts=50, successful_attempts=40, failed_attempts=10,
        success_rate=Decimal("0.8"), estimated_cost_usd=Decimal("0"), verdict=verdict,
    )


def _report(metrics):
    empty_effectiveness = DiscoveryEffectivenessReport(report_version="DEF-001", by_source=(), by_source_and_horizon=(), by_source_and_regime=())
    return ProviderQualityReport(version="PQ-001", computed_at=AS_OF, by_provider=tuple(metrics), health_statuses=(), ai_discovery_effectiveness=empty_effectiveness)


def test_severity_none_when_all_healthy(session):
    report = _report([_metric("yahoo-finance", "OK"), _metric("upstox-v3", "OK")])

    snapshot = record_outage_snapshot(
        session, data_type=DATA_TYPE, registered_provider_ids=("yahoo-finance", "upstox-v3"),
        quality_report=report, evaluated_at=AS_OF,
    )

    assert snapshot.severity == SEVERITY_NONE
    assert snapshot.degraded_provider_ids == []
    assert snapshot.snapshot_rule_version == OUTAGE_SNAPSHOT_VERSION


def test_severity_partial_when_some_degraded(session):
    report = _report([_metric("yahoo-finance", "OK"), _metric("upstox-v3", "WEAK")])

    snapshot = record_outage_snapshot(
        session, data_type=DATA_TYPE, registered_provider_ids=("yahoo-finance", "upstox-v3"),
        quality_report=report, evaluated_at=AS_OF,
    )

    assert snapshot.severity == SEVERITY_PARTIAL
    assert snapshot.degraded_provider_ids == ["upstox-v3"]
    assert snapshot.healthy_provider_count == 1


def test_severity_total_when_all_degraded(session):
    report = _report([_metric("yahoo-finance", "WEAK"), _metric("upstox-v3", "WEAK")])

    snapshot = record_outage_snapshot(
        session, data_type=DATA_TYPE, registered_provider_ids=("yahoo-finance", "upstox-v3"),
        quality_report=report, evaluated_at=AS_OF,
    )

    assert snapshot.severity == SEVERITY_TOTAL
    assert snapshot.healthy_provider_count == 0


def test_insufficient_sample_not_treated_as_degraded(session):
    report = _report([_metric("yahoo-finance", "INSUFFICIENT_SAMPLE"), _metric("upstox-v3", "OK")])

    snapshot = record_outage_snapshot(
        session, data_type=DATA_TYPE, registered_provider_ids=("yahoo-finance", "upstox-v3"),
        quality_report=report, evaluated_at=AS_OF,
    )

    assert snapshot.severity == SEVERITY_NONE


def test_provider_with_no_metric_at_all_treated_as_healthy(session):
    report = _report([_metric("upstox-v3", "OK")])  # yahoo-finance has no metric at all

    snapshot = record_outage_snapshot(
        session, data_type=DATA_TYPE, registered_provider_ids=("yahoo-finance", "upstox-v3"),
        quality_report=report, evaluated_at=AS_OF,
    )

    assert snapshot.severity == SEVERITY_NONE
    assert snapshot.healthy_provider_count == 2


def test_idempotent_and_history(session):
    report = _report([_metric("yahoo-finance", "OK")])

    first = record_outage_snapshot(session, data_type=DATA_TYPE, registered_provider_ids=("yahoo-finance",), quality_report=report, evaluated_at=AS_OF)
    second = record_outage_snapshot(session, data_type=DATA_TYPE, registered_provider_ids=("yahoo-finance",), quality_report=report, evaluated_at=AS_OF)
    record_outage_snapshot(session, data_type=DATA_TYPE, registered_provider_ids=("yahoo-finance",), quality_report=report, evaluated_at=AS_OF + timedelta(hours=1))

    assert first.id == second.id
    assert len(get_outage_history(session, DATA_TYPE)) == 2
    latest = get_latest_outage_snapshot(session, DATA_TYPE)
    assert latest.evaluated_at.replace(tzinfo=timezone.utc) == AS_OF + timedelta(hours=1)


def test_get_latest_outage_snapshot_none_when_no_history(session):
    assert get_latest_outage_snapshot(session, "UNKNOWN_TYPE") is None
