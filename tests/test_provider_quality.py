from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery_effectiveness import VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK
from app.fundamental_data.ingest import ingest_fundamental_data
from app.models import Stock
from app.provider_contracts import (
    CAPABILITY_FUNDAMENTAL_DATA,
    ProviderHealthStatus,
)
from app.provider_quality import (
    PROVIDER_QUALITY_VERSION,
    compute_provider_quality_report,
)
from app.refresh_policy import DATA_TYPE_FUNDAMENTAL, DATA_TYPE_MARKET, record_fetch_attempt
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)


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


class _FakeFundamentalsProvider:
    source = "alpha-vantage"
    capability = CAPABILITY_FUNDAMENTAL_DATA
    version = "1"

    def fetch_fundamentals(self, symbol):
        return None


class _HealthyProvider:
    source = "healthy-provider"

    def check_health(self):
        return ProviderHealthStatus(provider_id=self.source, is_available=True, checked_at=AS_OF, detail="ok")


def test_empty_platform_reports_no_provider_metrics(session):
    report = compute_provider_quality_report(session, computed_at=AS_OF)

    assert report.version == PROVIDER_QUALITY_VERSION
    assert report.by_provider == ()
    assert report.health_statuses == ()


def test_rows_without_provider_id_are_excluded_from_provider_metrics(session):
    record_fetch_attempt(
        session, data_type=DATA_TYPE_MARKET, scope_key="scope-1", requested_at=AS_OF,
        source_timestamp=AS_OF, success=True,
    )

    report = compute_provider_quality_report(session, computed_at=AS_OF)

    assert report.by_provider == ()


def test_reliable_provider_is_marked_ok_with_zero_cost(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        record_fetch_attempt(
            session, data_type=DATA_TYPE_FUNDAMENTAL, scope_key=f"scope-{i}", requested_at=AS_OF,
            source_timestamp=AS_OF, success=True, provider_id="alpha-vantage",
        )

    report = compute_provider_quality_report(session, computed_at=AS_OF)

    metric = next(m for m in report.by_provider if m.provider_id == "alpha-vantage")
    assert metric.data_type == DATA_TYPE_FUNDAMENTAL
    assert metric.total_attempts == total
    assert metric.successful_attempts == total
    assert metric.success_rate == Decimal("1")
    assert metric.verdict == VERDICT_OK
    assert metric.estimated_cost_usd == Decimal("0")


def test_unreliable_provider_is_marked_weak(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        record_fetch_attempt(
            session, data_type=DATA_TYPE_FUNDAMENTAL, scope_key=f"scope-{i}", requested_at=AS_OF,
            source_timestamp=None, success=(i < total // 4),
            failure_reason=None if i < total // 4 else "boom", provider_id="finnhub",
        )

    report = compute_provider_quality_report(session, computed_at=AS_OF)

    metric = next(m for m in report.by_provider if m.provider_id == "finnhub")
    assert metric.verdict == VERDICT_WEAK
    assert metric.failed_attempts == total - total // 4


def test_small_sample_is_marked_insufficient(session):
    record_fetch_attempt(
        session, data_type=DATA_TYPE_FUNDAMENTAL, scope_key="scope-0", requested_at=AS_OF,
        source_timestamp=AS_OF, success=True, provider_id="alpha-vantage",
    )

    report = compute_provider_quality_report(session, computed_at=AS_OF)

    metric = next(m for m in report.by_provider if m.provider_id == "alpha-vantage")
    assert metric.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_two_providers_for_the_same_capability_are_compared_independently(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        record_fetch_attempt(
            session, data_type=DATA_TYPE_FUNDAMENTAL, scope_key=f"good-{i}", requested_at=AS_OF,
            source_timestamp=AS_OF, success=True, provider_id="alpha-vantage",
        )
    for i in range(total):
        record_fetch_attempt(
            session, data_type=DATA_TYPE_FUNDAMENTAL, scope_key=f"bad-{i}", requested_at=AS_OF,
            source_timestamp=None, success=False, failure_reason="boom", provider_id="yahoo-finance",
        )

    report = compute_provider_quality_report(session, computed_at=AS_OF)

    good = next(m for m in report.by_provider if m.provider_id == "alpha-vantage")
    bad = next(m for m in report.by_provider if m.provider_id == "yahoo-finance")
    assert good.verdict == VERDICT_OK
    assert bad.verdict == VERDICT_WEAK


def test_unknown_provider_has_no_fabricated_cost(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        record_fetch_attempt(
            session, data_type=DATA_TYPE_FUNDAMENTAL, scope_key=f"scope-{i}", requested_at=AS_OF,
            source_timestamp=AS_OF, success=True, provider_id="some-future-paid-vendor",
        )

    report = compute_provider_quality_report(session, computed_at=AS_OF)

    metric = next(m for m in report.by_provider if m.provider_id == "some-future-paid-vendor")
    assert metric.estimated_cost_usd is None


def test_health_statuses_are_included_when_live_providers_supplied(session):
    provider = _HealthyProvider()

    report = compute_provider_quality_report(session, computed_at=AS_OF, providers=(provider,))

    assert report.health_statuses == (
        ProviderHealthStatus(provider_id="healthy-provider", is_available=True, checked_at=AS_OF, detail="ok"),
    )


def test_report_is_reproducible(session):
    record_fetch_attempt(
        session, data_type=DATA_TYPE_FUNDAMENTAL, scope_key="scope-1", requested_at=AS_OF,
        source_timestamp=AS_OF, success=True, provider_id="alpha-vantage",
    )

    first = compute_provider_quality_report(session, computed_at=AS_OF)
    second = compute_provider_quality_report(session, computed_at=AS_OF)

    assert first == second


def test_report_includes_ai_discovery_effectiveness(session):
    from app.discovery_effectiveness import DISCOVERY_EFFECTIVENESS_VERSION

    report = compute_provider_quality_report(session, computed_at=AS_OF)

    assert report.ai_discovery_effectiveness.report_version == DISCOVERY_EFFECTIVENESS_VERSION
    assert report.ai_discovery_effectiveness.by_source == ()


def test_report_never_writes_anything(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.commit()
    session.refresh(stock)
    before_count = session.query(Stock).count()

    compute_provider_quality_report(session, computed_at=AS_OF)

    assert session.query(Stock).count() == before_count


def test_ingest_fundamental_data_records_provider_id_on_the_fetch_attempt(session):
    from app.models import DataFetchAttempt

    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.commit()
    session.refresh(stock)

    ingest_fundamental_data(session, _FakeFundamentalsProvider(), stock, requested_at=AS_OF)

    attempt = session.query(DataFetchAttempt).one()
    assert attempt.provider_id == "alpha-vantage"
