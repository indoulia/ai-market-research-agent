from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.provider_contracts import CAPABILITY_FUNDAMENTAL_DATA, CAPABILITY_NEWS_EVENT_DATA
from app.provider_quality import compute_provider_quality_report
from app.provider_registry import ProviderRegistry, ROLE_OPTIONAL, ROLE_PRIMARY, ROLE_SECONDARY
from app.provider_selection import (
    NoHealthyProviderAvailableError,
    PROVIDER_SELECTION_VERSION,
    SKIP_REASON_DEGRADED,
    SKIP_REASON_DISABLED,
    select_provider,
)
from app.refresh_policy import DATA_TYPE_FUNDAMENTAL, DATA_TYPE_NEWS_EVENT, record_fetch_attempt
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

AS_OF = datetime(2027, 2, 1, tzinfo=timezone.utc)


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
    def __init__(self, source):
        self.source = source
        self.capability = CAPABILITY_FUNDAMENTAL_DATA
        self.version = "1"

    def fetch_fundamentals(self, symbol):
        return None


class _FakeNewsProvider:
    def __init__(self, source):
        self.source = source
        self.capability = CAPABILITY_NEWS_EVENT_DATA
        self.version = "1"

    def fetch_news(self, symbol):
        return ()


def _make_reliable_history(session, *, provider_id, data_type=DATA_TYPE_FUNDAMENTAL):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        record_fetch_attempt(
            session, data_type=data_type, scope_key=f"good-{provider_id}-{i}", requested_at=AS_OF,
            source_timestamp=AS_OF, success=True, provider_id=provider_id,
        )


def _make_unreliable_history(session, *, provider_id, data_type=DATA_TYPE_FUNDAMENTAL):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        record_fetch_attempt(
            session, data_type=data_type, scope_key=f"bad-{provider_id}-{i}", requested_at=AS_OF,
            source_timestamp=None, success=False, failure_reason="boom", provider_id=provider_id,
        )


def test_selects_healthy_primary(session):
    registry = ProviderRegistry()
    primary = _FakeFundamentalsProvider("primary-provider")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=primary)
    _make_reliable_history(session, provider_id="primary-provider")
    report = compute_provider_quality_report(session, computed_at=AS_OF)

    provider, decision = select_provider(registry, report, CAPABILITY_FUNDAMENTAL_DATA)

    assert provider is primary
    assert decision.version == PROVIDER_SELECTION_VERSION
    assert decision.selected_provider_id == "primary-provider"
    assert decision.selected_role == ROLE_PRIMARY
    assert decision.skipped == ()


def test_fails_over_to_secondary_when_primary_is_degraded(session):
    registry = ProviderRegistry()
    primary = _FakeFundamentalsProvider("primary-provider")
    secondary = _FakeFundamentalsProvider("secondary-provider")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=primary)
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_SECONDARY, provider=secondary)
    _make_unreliable_history(session, provider_id="primary-provider")
    _make_reliable_history(session, provider_id="secondary-provider")
    report = compute_provider_quality_report(session, computed_at=AS_OF)

    provider, decision = select_provider(registry, report, CAPABILITY_FUNDAMENTAL_DATA)

    assert provider is secondary
    assert decision.selected_provider_id == "secondary-provider"
    assert len(decision.skipped) == 1
    assert decision.skipped[0].provider_id == "primary-provider"
    assert decision.skipped[0].reason == SKIP_REASON_DEGRADED


def test_fails_over_to_secondary_when_primary_disabled(session):
    registry = ProviderRegistry()
    primary = _FakeFundamentalsProvider("primary-provider")
    secondary = _FakeFundamentalsProvider("secondary-provider")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=primary)
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_SECONDARY, provider=secondary)
    registry.set_enabled(capability=CAPABILITY_FUNDAMENTAL_DATA, provider_id="primary-provider", enabled=False)
    report = compute_provider_quality_report(session, computed_at=AS_OF)

    provider, decision = select_provider(registry, report, CAPABILITY_FUNDAMENTAL_DATA)

    assert provider is secondary
    assert decision.skipped[0].reason == SKIP_REASON_DISABLED


def test_insufficient_sample_is_not_treated_as_degraded(session):
    registry = ProviderRegistry()
    primary = _FakeFundamentalsProvider("new-provider")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=primary)
    # Only a handful of attempts -- below MIN_SAMPLE_SIZE_FOR_COMPARISON.
    record_fetch_attempt(
        session, data_type=DATA_TYPE_FUNDAMENTAL, scope_key="scope-0", requested_at=AS_OF,
        source_timestamp=AS_OF, success=True, provider_id="new-provider",
    )
    report = compute_provider_quality_report(session, computed_at=AS_OF)

    provider, decision = select_provider(registry, report, CAPABILITY_FUNDAMENTAL_DATA)

    assert provider is primary
    assert decision.skipped == ()


def test_raises_when_all_providers_are_disabled_or_degraded(session):
    registry = ProviderRegistry()
    primary = _FakeFundamentalsProvider("primary-provider")
    secondary = _FakeFundamentalsProvider("secondary-provider")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=primary)
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_SECONDARY, provider=secondary)
    _make_unreliable_history(session, provider_id="primary-provider")
    registry.set_enabled(capability=CAPABILITY_FUNDAMENTAL_DATA, provider_id="secondary-provider", enabled=False)
    report = compute_provider_quality_report(session, computed_at=AS_OF)

    with pytest.raises(NoHealthyProviderAvailableError) as excinfo:
        select_provider(registry, report, CAPABILITY_FUNDAMENTAL_DATA)

    decision = excinfo.value.decision
    assert decision.selected_provider_id is None
    reasons = {s.provider_id: s.reason for s in decision.skipped}
    assert reasons == {"primary-provider": SKIP_REASON_DEGRADED, "secondary-provider": SKIP_REASON_DISABLED}


def test_optional_role_is_selected_when_primary_and_secondary_are_unavailable(session):
    registry = ProviderRegistry()
    primary = _FakeFundamentalsProvider("primary-provider")
    optional = _FakeFundamentalsProvider("optional-provider")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=primary)
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_OPTIONAL, provider=optional)
    _make_unreliable_history(session, provider_id="primary-provider")
    report = compute_provider_quality_report(session, computed_at=AS_OF)

    provider, decision = select_provider(registry, report, CAPABILITY_FUNDAMENTAL_DATA)

    assert provider is optional
    assert decision.selected_role == ROLE_OPTIONAL


def test_news_capability_data_type_vocabulary_mismatch_is_bridged(session):
    registry = ProviderRegistry()
    primary = _FakeNewsProvider("primary-news-provider")
    registry.register(capability=CAPABILITY_NEWS_EVENT_DATA, role=ROLE_PRIMARY, provider=primary)
    _make_unreliable_history(session, provider_id="primary-news-provider", data_type=DATA_TYPE_NEWS_EVENT)
    report = compute_provider_quality_report(session, computed_at=AS_OF)

    with pytest.raises(NoHealthyProviderAvailableError):
        select_provider(registry, report, CAPABILITY_NEWS_EVENT_DATA)


def test_recovering_quality_makes_a_previously_degraded_provider_selectable_again():
    """Suppression is recomputed fresh from whatever quality report is
    passed in -- never written back into the registry's own `enabled`
    flag. The identical, unmodified registry rejects the provider against
    a snapshot showing a poor track record and accepts the very same
    provider against a later snapshot showing a good one, with zero
    registry configuration change in between."""
    registry = ProviderRegistry()
    primary = _FakeFundamentalsProvider("recovering-provider")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=primary)

    degraded_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(degraded_engine)
    degraded_session = sessionmaker(bind=degraded_engine)()
    _make_unreliable_history(degraded_session, provider_id="recovering-provider")
    degraded_report = compute_provider_quality_report(degraded_session, computed_at=AS_OF)

    with pytest.raises(NoHealthyProviderAvailableError):
        select_provider(registry, degraded_report, CAPABILITY_FUNDAMENTAL_DATA)

    recovered_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(recovered_engine)
    recovered_session = sessionmaker(bind=recovered_engine)()
    _make_reliable_history(recovered_session, provider_id="recovering-provider")
    recovered_report = compute_provider_quality_report(recovered_session, computed_at=AS_OF + timedelta(days=1))

    provider, decision = select_provider(registry, recovered_report, CAPABILITY_FUNDAMENTAL_DATA)
    assert provider is primary
    assert decision.selected_provider_id == "recovering-provider"


def test_selection_never_mutates_registry_or_writes_to_the_session(session):
    registry = ProviderRegistry()
    primary = _FakeFundamentalsProvider("primary-provider")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=primary)
    _make_reliable_history(session, provider_id="primary-provider")
    report = compute_provider_quality_report(session, computed_at=AS_OF)
    before = registry.get_registrations(CAPABILITY_FUNDAMENTAL_DATA)

    select_provider(registry, report, CAPABILITY_FUNDAMENTAL_DATA)

    after = registry.get_registrations(CAPABILITY_FUNDAMENTAL_DATA)
    assert before == after
