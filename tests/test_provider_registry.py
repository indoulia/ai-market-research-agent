from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.fundamental_data.ingest import FUNDAMENTAL_INGESTION_VERSION
from app.models import FundamentalDataRecord, Stock
from app.provider_contracts import CAPABILITY_FUNDAMENTAL_DATA, CAPABILITY_MARKET_DATA, CAPABILITY_NEWS_EVENT_DATA
from app.provider_registry import (
    InvalidProviderConfigurationError,
    NoProviderAvailableError,
    ProviderRegistry,
    ROLE_OPTIONAL,
    ROLE_PRIMARY,
    ROLE_SECONDARY,
)

AS_OF = datetime(2027, 8, 1, tzinfo=timezone.utc)


class _FakeFundamentalsProvider:
    def __init__(self, source):
        self.source = source
        self.capability = CAPABILITY_FUNDAMENTAL_DATA
        self.version = "1"

    def fetch_fundamentals(self, symbol):
        return None


class _FakeMarketDataProvider:
    def __init__(self, source):
        self.source = source
        self.capability = CAPABILITY_MARKET_DATA
        self.version = "1"

    def fetch_daily_candles(self, symbol, from_date, to_date):
        return []


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


def test_register_rejects_wrong_capability():
    registry = ProviderRegistry()
    provider = _FakeFundamentalsProvider("fake-1")

    with pytest.raises(InvalidProviderConfigurationError):
        registry.register(capability=CAPABILITY_MARKET_DATA, role=ROLE_PRIMARY, provider=provider)


def test_register_rejects_unknown_role():
    registry = ProviderRegistry()
    provider = _FakeFundamentalsProvider("fake-1")

    with pytest.raises(InvalidProviderConfigurationError):
        registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role="TERTIARY", provider=provider)


def test_register_rejects_duplicate_role_and_provider():
    registry = ProviderRegistry()
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=_FakeFundamentalsProvider("fake-1"))

    with pytest.raises(InvalidProviderConfigurationError):
        registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=_FakeFundamentalsProvider("fake-1"))


def test_resolve_provider_prefers_primary_over_secondary():
    registry = ProviderRegistry()
    primary = _FakeFundamentalsProvider("primary-provider")
    secondary = _FakeFundamentalsProvider("secondary-provider")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_SECONDARY, provider=secondary)
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=primary)

    resolved = registry.resolve_provider(CAPABILITY_FUNDAMENTAL_DATA)

    assert resolved is primary


def test_resolve_provider_falls_back_when_primary_disabled():
    registry = ProviderRegistry()
    primary = _FakeFundamentalsProvider("primary-provider")
    secondary = _FakeFundamentalsProvider("secondary-provider")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=primary)
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_SECONDARY, provider=secondary)
    registry.set_enabled(capability=CAPABILITY_FUNDAMENTAL_DATA, provider_id="primary-provider", enabled=False)

    resolved = registry.resolve_provider(CAPABILITY_FUNDAMENTAL_DATA)

    assert resolved is secondary


def test_resolve_provider_raises_when_none_enabled():
    registry = ProviderRegistry()
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=_FakeFundamentalsProvider("primary-provider"))
    registry.set_enabled(capability=CAPABILITY_FUNDAMENTAL_DATA, provider_id="primary-provider", enabled=False)

    with pytest.raises(NoProviderAvailableError):
        registry.resolve_provider(CAPABILITY_FUNDAMENTAL_DATA)


def test_resolve_provider_raises_for_unconfigured_capability():
    registry = ProviderRegistry()

    with pytest.raises(NoProviderAvailableError):
        registry.resolve_provider(CAPABILITY_FUNDAMENTAL_DATA)


def test_preferred_role_selection():
    registry = ProviderRegistry()
    primary = _FakeFundamentalsProvider("primary-provider")
    optional = _FakeFundamentalsProvider("optional-provider")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=primary)
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_OPTIONAL, provider=optional)

    resolved = registry.resolve_provider(CAPABILITY_FUNDAMENTAL_DATA, preferred_role=ROLE_OPTIONAL)

    assert resolved is optional


def test_capability_level_routing_is_independent_per_capability():
    registry = ProviderRegistry()
    fundamentals_provider = _FakeFundamentalsProvider("fund-primary")
    market_provider = _FakeMarketDataProvider("market-primary")
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=fundamentals_provider)
    registry.register(capability=CAPABILITY_MARKET_DATA, role=ROLE_PRIMARY, provider=market_provider)

    assert registry.resolve_provider(CAPABILITY_FUNDAMENTAL_DATA) is fundamentals_provider
    assert registry.resolve_provider(CAPABILITY_MARKET_DATA) is market_provider
    with pytest.raises(NoProviderAvailableError):
        registry.resolve_provider(CAPABILITY_NEWS_EVENT_DATA)


def test_configuration_change_does_not_rewrite_historical_records(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.commit()
    session.refresh(stock)
    session.add(FundamentalDataRecord(
        stock_id=stock.id, source="alpha-vantage", period_end_date=None, revenue=None, net_income=None, eps=None,
        gross_margin=None, operating_margin=None, net_margin=None, debt_to_equity=None, free_cash_flow=None,
        pe_ratio=None, price_to_book=None, published_at=AS_OF, fetched_at=AS_OF,
        ingestion_rule_version=FUNDAMENTAL_INGESTION_VERSION,
    ))
    session.commit()

    registry = ProviderRegistry()
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_PRIMARY, provider=_FakeFundamentalsProvider("alpha-vantage"))
    registry.register(capability=CAPABILITY_FUNDAMENTAL_DATA, role=ROLE_SECONDARY, provider=_FakeFundamentalsProvider("yahoo-finance"))
    # switch which provider is primary going forward
    registry.set_enabled(capability=CAPABILITY_FUNDAMENTAL_DATA, provider_id="alpha-vantage", enabled=False)

    record = session.query(FundamentalDataRecord).one()
    assert record.source == "alpha-vantage"  # untouched by the registry config change
    assert registry.resolve_provider(CAPABILITY_FUNDAMENTAL_DATA).source == "yahoo-finance"
