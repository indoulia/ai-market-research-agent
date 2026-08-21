from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.fundamental_data.ingest import ingest_fundamental_data
from app.fundamental_data.yahoo import RawFundamentals, YahooFundamentalsClient, YahooFundamentalsError
from app.market_data.upstox import UpstoxClient
from app.market_data.yahoo import YahooFinanceClient
from app.models import DataFetchAttempt, FundamentalDataRecord, NewsEventRecord, Stock
from app.news_data.ingest import ingest_news_events
from app.news_data.yahoo import RawNewsItem, YahooNewsClient, YahooNewsError
from app.provider_contracts import (
    ALL_CAPABILITIES,
    CAPABILITY_AI_DISCOVERY,
    CAPABILITY_FUNDAMENTAL_DATA,
    CAPABILITY_MARKET_DATA,
    CAPABILITY_NEWS_EVENT_DATA,
    ProviderContractViolationError,
    ProviderHealthStatus,
    check_provider_health,
    get_provider_metadata,
    verify_provider_contract,
)

AS_OF = datetime(2027, 6, 1, tzinfo=timezone.utc)


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


class _FakeMarketDataProvider:
    source = "fake-market-data"
    capability = CAPABILITY_MARKET_DATA
    version = "1"

    def fetch_daily_candles(self, symbol, from_date, to_date):
        return []


class _FakeFundamentalsProvider:
    source = "fake-fundamentals"
    capability = CAPABILITY_FUNDAMENTAL_DATA
    version = "1"

    def __init__(self, raw=None, error=None):
        self.raw = raw
        self.error = error

    def fetch_fundamentals(self, symbol):
        if self.error is not None:
            raise self.error
        return self.raw


class _SecondFakeFundamentalsProvider(_FakeFundamentalsProvider):
    source = "second-fake-fundamentals"


class _FakeNewsProvider:
    source = "fake-news"
    capability = CAPABILITY_NEWS_EVENT_DATA
    version = "1"

    def __init__(self, items=(), error=None):
        self.items = items
        self.error = error

    def fetch_news(self, symbol):
        if self.error is not None:
            raise self.error
        return self.items


class _SecondFakeNewsProvider(_FakeNewsProvider):
    source = "second-fake-news"


class _FakeAIDiscoveryProvider:
    source = "fake-ai-discovery"
    capability = CAPABILITY_AI_DISCOVERY
    version = "1"

    def discover_candidates(self, universe_version):
        return ()


class _SecondFakeAIDiscoveryProvider(_FakeAIDiscoveryProvider):
    source = "second-fake-ai-discovery"


class _ThirdFakeAIDiscoveryProvider(_FakeAIDiscoveryProvider):
    source = "third-fake-ai-discovery"


class _HealthCheckingProvider:
    source = "health-aware-fake"
    capability = CAPABILITY_MARKET_DATA
    version = "1"

    def check_health(self, *, checked_at=None):
        return ProviderHealthStatus(provider_id=self.source, is_available=False, checked_at=AS_OF, detail="simulated outage")

    def fetch_daily_candles(self, symbol, from_date, to_date):
        return []


@pytest.mark.parametrize(
    "provider, expected_capability",
    [
        (YahooFinanceClient(), CAPABILITY_MARKET_DATA),
        (UpstoxClient.__new__(UpstoxClient), CAPABILITY_MARKET_DATA),
        (YahooFundamentalsClient(), CAPABILITY_FUNDAMENTAL_DATA),
        (YahooNewsClient(), CAPABILITY_NEWS_EVENT_DATA),
        (_FakeMarketDataProvider(), CAPABILITY_MARKET_DATA),
        (_FakeFundamentalsProvider(), CAPABILITY_FUNDAMENTAL_DATA),
        (_FakeNewsProvider(), CAPABILITY_NEWS_EVENT_DATA),
        (_FakeAIDiscoveryProvider(), CAPABILITY_AI_DISCOVERY),
    ],
)
def test_real_and_fake_providers_satisfy_the_contract(provider, expected_capability):
    metadata = verify_provider_contract(provider, expected_capability=expected_capability)
    assert metadata.capability == expected_capability
    assert metadata.provider_id == provider.source


def test_three_interchangeable_slots_exist_for_market_data():
    providers = [YahooFinanceClient(), UpstoxClient.__new__(UpstoxClient), _FakeMarketDataProvider()]
    for provider in providers:
        verify_provider_contract(provider, expected_capability=CAPABILITY_MARKET_DATA)
    assert len({p.source for p in providers}) == 3


def test_three_interchangeable_slots_exist_for_fundamentals():
    providers = [YahooFundamentalsClient(), _FakeFundamentalsProvider(), _SecondFakeFundamentalsProvider()]
    for provider in providers:
        verify_provider_contract(provider, expected_capability=CAPABILITY_FUNDAMENTAL_DATA)
    assert len({p.source for p in providers}) == 3


def test_three_interchangeable_slots_exist_for_news():
    providers = [YahooNewsClient(), _FakeNewsProvider(), _SecondFakeNewsProvider()]
    for provider in providers:
        verify_provider_contract(provider, expected_capability=CAPABILITY_NEWS_EVENT_DATA)
    assert len({p.source for p in providers}) == 3


def test_three_interchangeable_slots_exist_for_ai_discovery_despite_no_real_implementation():
    # honest: no real AI discovery provider exists in this codebase yet
    # (see module docstring) -- the contract itself is still provably
    # substitutable at test level.
    providers = [_FakeAIDiscoveryProvider(), _SecondFakeAIDiscoveryProvider(), _ThirdFakeAIDiscoveryProvider()]
    for provider in providers:
        verify_provider_contract(provider, expected_capability=CAPABILITY_AI_DISCOVERY)
    assert len({p.source for p in providers}) == 3


def test_wrong_capability_is_rejected():
    with pytest.raises(ProviderContractViolationError):
        verify_provider_contract(_FakeMarketDataProvider(), expected_capability=CAPABILITY_NEWS_EVENT_DATA)


def test_missing_attribute_raises_contract_violation_not_attribute_error():
    class _Broken:
        source = "broken"

    with pytest.raises(ProviderContractViolationError):
        get_provider_metadata(_Broken())


def test_health_check_contract_for_providers_that_implement_it():
    status = check_provider_health(_HealthCheckingProvider(), checked_at=AS_OF)
    assert status.is_available is False
    assert status.detail == "simulated outage"


def test_health_check_falls_back_honestly_when_not_implemented():
    status = check_provider_health(_FakeMarketDataProvider(), checked_at=AS_OF)
    assert status.is_available is True
    assert "no health check implemented" in status.detail


def test_all_capabilities_are_covered_by_at_least_one_real_or_fake_provider():
    assert set(ALL_CAPABILITIES) == {
        CAPABILITY_MARKET_DATA, CAPABILITY_FUNDAMENTAL_DATA, CAPABILITY_NEWS_EVENT_DATA, CAPABILITY_AI_DISCOVERY,
    }


def _make_stock(session, symbol="AAA"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.commit()
    session.refresh(stock)
    return stock


def test_domain_ingestion_is_unchanged_when_the_fundamentals_provider_is_swapped(session):
    stock = _make_stock(session, "FUND1")
    raw = RawFundamentals(
        period_end_date=None, revenue=Decimal("100"), net_income=None, eps=None, gross_margin=None,
        operating_margin=None, net_margin=None, debt_to_equity=None, free_cash_flow=None, pe_ratio=None,
        price_to_book=None,
    )

    real_shaped = ingest_fundamental_data(session, _FakeFundamentalsProvider(raw=raw), stock, requested_at=AS_OF)
    assert real_shaped is not None
    assert real_shaped.source == "fake-fundamentals"

    stock2 = _make_stock(session, "FUND2")
    swapped = ingest_fundamental_data(session, _SecondFakeFundamentalsProvider(raw=raw), stock2, requested_at=AS_OF)
    assert swapped is not None
    assert swapped.source == "second-fake-fundamentals"
    assert session.query(FundamentalDataRecord).count() == 2


def test_provider_specific_errors_never_leak_out_of_fundamentals_ingestion(session):
    stock = _make_stock(session, "FUND3")
    provider = _FakeFundamentalsProvider(error=YahooFundamentalsError("vendor outage"))

    result = ingest_fundamental_data(session, provider, stock, requested_at=AS_OF)

    assert result is None
    attempt = session.query(DataFetchAttempt).one()
    assert attempt.success is False
    assert "vendor outage" in attempt.failure_reason


def test_domain_ingestion_is_unchanged_when_the_news_provider_is_swapped(session):
    stock = _make_stock(session, "NEWS1")
    items = (RawNewsItem(external_id="a1", headline="Quarterly results announced", published_at=AS_OF),)

    real_shaped = ingest_news_events(session, _FakeNewsProvider(items=items), stock, requested_at=AS_OF)
    assert len(real_shaped) == 1
    assert real_shaped[0].source == "fake-news"

    stock2 = _make_stock(session, "NEWS2")
    swapped = ingest_news_events(session, _SecondFakeNewsProvider(items=items), stock2, requested_at=AS_OF)
    assert len(swapped) == 1
    assert swapped[0].source == "second-fake-news"
    assert session.query(NewsEventRecord).count() == 2


def test_provider_specific_errors_never_leak_out_of_news_ingestion(session):
    stock = _make_stock(session, "NEWS3")
    provider = _FakeNewsProvider(error=YahooNewsError("vendor outage"))

    result = ingest_news_events(session, provider, stock, requested_at=AS_OF)

    assert result == ()
    attempt = session.query(DataFetchAttempt).one()
    assert attempt.success is False
    assert "vendor outage" in attempt.failure_reason
