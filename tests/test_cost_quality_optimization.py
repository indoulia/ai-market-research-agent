from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cost_quality_optimization import (
    COST_QUALITY_VERSION,
    VERDICT_COST_OPTIMIZED_SELECTION,
    VERDICT_NO_ACCEPTABLE_PROVIDER,
    VERDICT_QUALITY_JUSTIFIES_COST,
    compute_cost_quality_tradeoff,
    get_cost_quality_history,
)
from app.data_source_reliability import RELIABILITY_SUCCESS_THRESHOLD
from app.db import Base
from app.discovery_effectiveness import DiscoveryEffectivenessReport
from app.provider_quality import ProviderQualityMetric, ProviderQualityReport

AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
DATA_TYPE = "FUNDAMENTAL_DATA"


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


def _metric(provider_id, verdict, success_rate=Decimal("0.95")):
    return ProviderQualityMetric(
        data_type=DATA_TYPE, provider_id=provider_id, total_attempts=50, successful_attempts=45, failed_attempts=5,
        success_rate=success_rate, estimated_cost_usd=Decimal("0"), verdict=verdict,
    )


def _report(metrics):
    effectiveness = DiscoveryEffectivenessReport(report_version="DEF-001", by_source=(), by_source_and_horizon=(), by_source_and_regime=())
    return ProviderQualityReport(version="PQ-001", computed_at=AS_OF, by_provider=tuple(metrics), health_statuses=(), ai_discovery_effectiveness=effectiveness)


def test_cost_optimized_selection_when_free_provider_acceptable(session):
    report = _report([_metric("yahoo-finance", "OK", Decimal("0.92")), _metric("alpha-vantage", "OK", Decimal("0.95"))])

    result = compute_cost_quality_tradeoff(session, data_type=DATA_TYPE, quality_report=report, computed_at=AS_OF)

    assert result.verdict == VERDICT_COST_OPTIMIZED_SELECTION
    assert result.recommended_provider_id == "alpha-vantage"  # both free, alpha-vantage has the higher success rate
    assert result.best_free_provider_id == "alpha-vantage"
    assert result.quality_floor == RELIABILITY_SUCCESS_THRESHOLD
    assert result.report_rule_version == COST_QUALITY_VERSION


def test_weak_provider_never_recommended_despite_being_free(session):
    report = _report([_metric("yahoo-finance", "WEAK", Decimal("0.50")), _metric("alpha-vantage", "OK", Decimal("0.92"))])

    result = compute_cost_quality_tradeoff(session, data_type=DATA_TYPE, quality_report=report, computed_at=AS_OF)

    assert result.recommended_provider_id == "alpha-vantage"
    assert result.recommended_provider_id != "yahoo-finance"


def test_no_acceptable_provider_when_all_weak(session):
    report = _report([_metric("yahoo-finance", "WEAK", Decimal("0.40")), _metric("alpha-vantage", "WEAK", Decimal("0.30"))])

    result = compute_cost_quality_tradeoff(session, data_type=DATA_TYPE, quality_report=report, computed_at=AS_OF)

    assert result.verdict == VERDICT_NO_ACCEPTABLE_PROVIDER
    assert result.recommended_provider_id is None
    assert result.best_free_provider_id is None


def test_quality_justifies_cost_when_no_free_acceptable_but_paid_exists(session, monkeypatch):
    import app.cost_quality_optimization as module
    monkeypatch.setattr(module, "PROVIDER_COST_PER_REQUEST_USD", {
        "yahoo-finance": Decimal("0"), "premium-provider": Decimal("0.05"),
    })
    report = _report([_metric("yahoo-finance", "WEAK", Decimal("0.40")), _metric("premium-provider", "OK", Decimal("0.95"))])

    result = compute_cost_quality_tradeoff(session, data_type=DATA_TYPE, quality_report=report, computed_at=AS_OF)

    assert result.verdict == VERDICT_QUALITY_JUSTIFIES_COST
    assert result.recommended_provider_id == "premium-provider"
    assert result.best_free_provider_id is None


def test_provider_with_unknown_cost_excluded_from_recommendation(session, monkeypatch):
    import app.cost_quality_optimization as module
    monkeypatch.setattr(module, "PROVIDER_COST_PER_REQUEST_USD", {})  # neither provider's cost is known
    report = _report([_metric("mystery-provider", "OK", Decimal("0.95"))])

    result = compute_cost_quality_tradeoff(session, data_type=DATA_TYPE, quality_report=report, computed_at=AS_OF)

    assert result.verdict == VERDICT_NO_ACCEPTABLE_PROVIDER
    assert result.recommended_provider_id is None


def test_report_history_accumulates(session):
    report = _report([_metric("yahoo-finance", "OK")])

    compute_cost_quality_tradeoff(session, data_type=DATA_TYPE, quality_report=report, computed_at=AS_OF)
    compute_cost_quality_tradeoff(session, data_type=DATA_TYPE, quality_report=report, computed_at=AS_OF)

    assert len(get_cost_quality_history(session, DATA_TYPE)) == 2
