from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_discovery import DOCUMENTED_UNIMPLEMENTED_PROVIDERS, OllamaDiscoveryClient, OllamaDiscoveryError
from app.db import Base
from app.fundamental_data.alpha_vantage import (
    AlphaVantageCredentialsError,
    AlphaVantageError,
    AlphaVantageFundamentalsClient,
)
from app.fundamental_data.ingest import ingest_fundamental_data
from app.market_data.stooq import StooqClient, StooqError
from app.models import DataFetchAttempt, FundamentalDataRecord, NewsEventRecord, Stock
from app.news_data.finnhub import FinnhubCredentialsError, FinnhubError, FinnhubNewsClient
from app.news_data.ingest import ingest_news_events
from app.provider_contracts import (
    CAPABILITY_AI_DISCOVERY,
    CAPABILITY_FUNDAMENTAL_DATA,
    CAPABILITY_MARKET_DATA,
    CAPABILITY_NEWS_EVENT_DATA,
    verify_provider_contract,
)

AS_OF = datetime(2027, 7, 1, tzinfo=timezone.utc)


class _FakeResponse:
    def __init__(self, *, text=None, json_data=None, status_error=None):
        self.text = text
        self._json_data = json_data
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    def json(self):
        return self._json_data


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


def _make_stock(session, symbol="AAA", instrument_key="NSE_EQ|AAA"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, instrument_key=instrument_key)
    session.add(stock)
    session.commit()
    session.refresh(stock)
    return stock


# ---------------------------------------------------------------------------
# StooqClient (market data)
# ---------------------------------------------------------------------------


def test_stooq_client_satisfies_the_market_data_contract():
    verify_provider_contract(StooqClient(), expected_capability=CAPABILITY_MARKET_DATA)


def test_stooq_client_parses_real_csv_shape(monkeypatch):
    csv_body = (
        "Date,Open,High,Low,Close,Volume\n"
        "2027-06-01,100.0,101.0,99.0,100.5,1000\n"
        "2027-06-02,100.5,102.0,100.0,101.5,1200\n"
    )
    monkeypatch.setattr("app.market_data.stooq.httpx.get", lambda *a, **k: _FakeResponse(text=csv_body))

    candles = StooqClient().fetch_daily_candles("reliance.ns", date(2027, 6, 1), date(2027, 6, 2))

    assert len(candles) == 2
    assert candles[0][1:] == [100.0, 101.0, 99.0, 100.5, 1000]


def test_stooq_client_wraps_provider_errors(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr("app.market_data.stooq.httpx.get", _boom)

    with pytest.raises(StooqError):
        StooqClient().fetch_daily_candles("RELIANCE.NS", date(2027, 6, 1), date(2027, 6, 2))


def test_stooq_output_matches_the_same_contract_shape_yahoo_uses(monkeypatch):
    # app.market_data.ingest.ingest_daily_history consumes any
    # DailyHistoryProvider identically -- proven here at the shape level
    # (list[timestamp_iso, open, high, low, close, volume]), the exact
    # contract `test_yahoo_client.py` already exercises for Yahoo. A live
    # `ingest_daily_history` DB round-trip is out of scope here: that
    # function's own upsert already relies on Postgres-specific SQL
    # (pre-existing, unrelated to this EPIC's provider-contract scope).
    csv_body = "Date,Open,High,Low,Close,Volume\n2027-06-01,100.0,101.0,99.0,100.5,1000\n"
    monkeypatch.setattr("app.market_data.stooq.httpx.get", lambda *a, **k: _FakeResponse(text=csv_body))

    candles = StooqClient().fetch_daily_candles("RELIANCE.NS", date(2027, 6, 1), date(2027, 6, 1))

    assert len(candles) == 1
    timestamp_iso, open_, high, low, close, volume = candles[0]
    assert isinstance(timestamp_iso, str)
    assert [open_, high, low, close, volume] == [100.0, 101.0, 99.0, 100.5, 1000]


# ---------------------------------------------------------------------------
# AlphaVantageFundamentalsClient
# ---------------------------------------------------------------------------


def test_alpha_vantage_client_requires_credentials():
    with pytest.raises(AlphaVantageCredentialsError):
        AlphaVantageFundamentalsClient(api_key="")


def test_alpha_vantage_client_satisfies_the_fundamental_data_contract():
    verify_provider_contract(
        AlphaVantageFundamentalsClient(api_key="test-key"), expected_capability=CAPABILITY_FUNDAMENTAL_DATA
    )


def test_alpha_vantage_client_maps_real_payload_shape(monkeypatch):
    payload = {
        "Symbol": "AAA", "RevenueTTM": "1000000", "GrossProfitTTM": "400000", "EPS": "12.5",
        "OperatingMarginTTM": "0.25", "ProfitMargin": "0.15", "PERatio": "22.3", "PriceToBookRatio": "4.1",
        "LatestQuarter": "2027-03-31",
    }
    monkeypatch.setattr(
        "app.fundamental_data.alpha_vantage.httpx.get", lambda *a, **k: _FakeResponse(json_data=payload)
    )

    raw = AlphaVantageFundamentalsClient(api_key="test-key").fetch_fundamentals("AAA")

    assert raw.revenue == Decimal("1000000")
    assert raw.gross_margin == Decimal("0.4")
    assert raw.eps == Decimal("12.5")
    assert raw.period_end_date == date(2027, 3, 31)


def test_alpha_vantage_client_returns_none_for_unknown_symbol(monkeypatch):
    monkeypatch.setattr("app.fundamental_data.alpha_vantage.httpx.get", lambda *a, **k: _FakeResponse(json_data={}))

    assert AlphaVantageFundamentalsClient(api_key="test-key").fetch_fundamentals("UNKNOWN") is None


def test_alpha_vantage_client_wraps_provider_errors(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("rate limited")

    monkeypatch.setattr("app.fundamental_data.alpha_vantage.httpx.get", _boom)

    with pytest.raises(AlphaVantageError):
        AlphaVantageFundamentalsClient(api_key="test-key").fetch_fundamentals("AAA")


def test_fundamental_ingestion_is_unchanged_when_alpha_vantage_is_used(session, monkeypatch):
    stock = _make_stock(session, "BBB")
    payload = {"Symbol": "BBB", "RevenueTTM": "500000", "EPS": "5.0"}
    monkeypatch.setattr(
        "app.fundamental_data.alpha_vantage.httpx.get", lambda *a, **k: _FakeResponse(json_data=payload)
    )

    record = ingest_fundamental_data(session, AlphaVantageFundamentalsClient(api_key="test-key"), stock, requested_at=AS_OF)

    assert record.source == "alpha-vantage"
    assert record.revenue == Decimal("500000")
    assert session.query(FundamentalDataRecord).count() == 1


def test_alpha_vantage_errors_never_leak_out_of_fundamentals_ingestion(session, monkeypatch):
    stock = _make_stock(session, "CCC")

    def _boom(*a, **k):
        raise RuntimeError("vendor outage")

    monkeypatch.setattr("app.fundamental_data.alpha_vantage.httpx.get", _boom)

    result = ingest_fundamental_data(session, AlphaVantageFundamentalsClient(api_key="test-key"), stock, requested_at=AS_OF)

    assert result is None
    attempt = session.query(DataFetchAttempt).one()
    assert attempt.success is False
    assert session.query(FundamentalDataRecord).count() == 0


# ---------------------------------------------------------------------------
# FinnhubNewsClient
# ---------------------------------------------------------------------------


def test_finnhub_client_requires_credentials():
    with pytest.raises(FinnhubCredentialsError):
        FinnhubNewsClient(api_key="")


def test_finnhub_client_satisfies_the_news_contract():
    verify_provider_contract(FinnhubNewsClient(api_key="test-key"), expected_capability=CAPABILITY_NEWS_EVENT_DATA)


def test_finnhub_client_maps_real_payload_shape(monkeypatch):
    payload = [
        {"id": 111, "headline": "Company posts record earnings", "datetime": 1750000000},
        {"id": 222, "headline": "missing time"},
    ]
    monkeypatch.setattr("app.news_data.finnhub.httpx.get", lambda *a, **k: _FakeResponse(json_data=payload))

    items = FinnhubNewsClient(api_key="test-key").fetch_news("AAA")

    assert len(items) == 1
    assert items[0].external_id == "111"
    assert items[0].headline == "Company posts record earnings"


def test_finnhub_client_wraps_provider_errors(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("timeout")

    monkeypatch.setattr("app.news_data.finnhub.httpx.get", _boom)

    with pytest.raises(FinnhubError):
        FinnhubNewsClient(api_key="test-key").fetch_news("AAA")


def test_news_ingestion_is_unchanged_when_finnhub_is_used(session, monkeypatch):
    stock = _make_stock(session, "DDD")
    payload = [{"id": 333, "headline": "Merger agreement announced", "datetime": 1750000000}]
    monkeypatch.setattr("app.news_data.finnhub.httpx.get", lambda *a, **k: _FakeResponse(json_data=payload))

    records = ingest_news_events(session, FinnhubNewsClient(api_key="test-key"), stock, requested_at=AS_OF)

    assert len(records) == 1
    assert records[0].source == "finnhub"
    assert session.query(NewsEventRecord).count() == 1


def test_finnhub_errors_never_leak_out_of_news_ingestion(session, monkeypatch):
    stock = _make_stock(session, "EEE")

    def _boom(*a, **k):
        raise RuntimeError("vendor outage")

    monkeypatch.setattr("app.news_data.finnhub.httpx.get", _boom)

    records = ingest_news_events(session, FinnhubNewsClient(api_key="test-key"), stock, requested_at=AS_OF)

    assert records == ()
    attempt = session.query(DataFetchAttempt).one()
    assert attempt.success is False


# ---------------------------------------------------------------------------
# OllamaDiscoveryClient
# ---------------------------------------------------------------------------


def test_ollama_client_satisfies_the_ai_discovery_contract():
    verify_provider_contract(OllamaDiscoveryClient(model="llama3"), expected_capability=CAPABILITY_AI_DISCOVERY)


def test_ollama_client_parses_real_response_shape(monkeypatch):
    monkeypatch.setattr(
        "app.ai_discovery.ollama.httpx.post",
        lambda *a, **k: _FakeResponse(json_data={"response": "RELIANCE: strong breakout on volume\nTCS: bullish reversal"}),
    )

    candidates = OllamaDiscoveryClient(model="llama3").discover_candidates("DCS-001")

    assert candidates == (
        {"symbol": "RELIANCE", "rationale": "strong breakout on volume"},
        {"symbol": "TCS", "rationale": "bullish reversal"},
    )


def test_ollama_client_skips_unparseable_lines(monkeypatch):
    monkeypatch.setattr(
        "app.ai_discovery.ollama.httpx.post",
        lambda *a, **k: _FakeResponse(json_data={"response": "not a valid line\nINFY: real signal here"}),
    )

    candidates = OllamaDiscoveryClient(model="llama3").discover_candidates("DCS-001")

    assert candidates == ({"symbol": "INFY", "rationale": "real signal here"},)


def test_ollama_client_wraps_provider_errors(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("model not found")

    monkeypatch.setattr("app.ai_discovery.ollama.httpx.post", _boom)

    with pytest.raises(OllamaDiscoveryError):
        OllamaDiscoveryClient(model="llama3").discover_candidates("DCS-001")


def test_documented_but_unimplemented_ai_providers_are_named_honestly():
    assert "openai" in DOCUMENTED_UNIMPLEMENTED_PROVIDERS
    assert "anthropic-claude" in DOCUMENTED_UNIMPLEMENTED_PROVIDERS
