from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.fundamental_data.yahoo import YahooFundamentalsClient, YahooFundamentalsError


class _FakeTicker:
    def __init__(self, info):
        self.info = info


def test_fetch_fundamentals_maps_all_known_fields(monkeypatch):
    quarter_end = datetime(2026, 6, 30, tzinfo=timezone.utc)
    info = {
        "totalRevenue": 1_000_000_000,
        "netIncomeToCommon": 150_000_000,
        "trailingEps": 12.5,
        "grossMargins": 0.42,
        "operatingMargins": 0.28,
        "profitMargins": 0.15,
        "debtToEquity": 35.2,
        "freeCashflow": 90_000_000,
        "trailingPE": 22.3,
        "priceToBook": 4.1,
        "mostRecentQuarter": int(quarter_end.timestamp()),
    }
    monkeypatch.setattr("app.fundamental_data.yahoo.yf.Ticker", lambda symbol: _FakeTicker(info))

    result = YahooFundamentalsClient().fetch_fundamentals("reliance.ns")

    assert result.period_end_date == date(2026, 6, 30)
    assert result.revenue == Decimal("1000000000")
    assert result.net_income == Decimal("150000000")
    assert result.eps == Decimal("12.5")
    assert result.gross_margin == Decimal("0.42")
    assert result.debt_to_equity == Decimal("35.2")
    assert result.free_cash_flow == Decimal("90000000")
    assert result.pe_ratio == Decimal("22.3")
    assert result.price_to_book == Decimal("4.1")


def test_fetch_fundamentals_handles_partial_coverage(monkeypatch):
    info = {"totalRevenue": 500_000_000}
    monkeypatch.setattr("app.fundamental_data.yahoo.yf.Ticker", lambda symbol: _FakeTicker(info))

    result = YahooFundamentalsClient().fetch_fundamentals("TCS.NS")

    assert result.revenue == Decimal("500000000")
    assert result.eps is None
    assert result.debt_to_equity is None
    assert result.period_end_date is None


def test_fetch_fundamentals_returns_none_for_empty_info(monkeypatch):
    monkeypatch.setattr("app.fundamental_data.yahoo.yf.Ticker", lambda symbol: _FakeTicker({}))

    assert YahooFundamentalsClient().fetch_fundamentals("UNKNOWN.NS") is None


def test_fetch_fundamentals_treats_nan_as_missing(monkeypatch):
    info = {"totalRevenue": float("nan"), "trailingEps": 5.0}
    monkeypatch.setattr("app.fundamental_data.yahoo.yf.Ticker", lambda symbol: _FakeTicker(info))

    result = YahooFundamentalsClient().fetch_fundamentals("INFY.NS")

    assert result.revenue is None
    assert result.eps == Decimal("5.0")


def test_fetch_fundamentals_rejects_empty_symbol():
    with pytest.raises(ValueError, match="symbol"):
        YahooFundamentalsClient().fetch_fundamentals("   ")


def test_fetch_fundamentals_wraps_provider_errors(monkeypatch):
    def _boom(symbol):
        raise RuntimeError("network down")

    monkeypatch.setattr("app.fundamental_data.yahoo.yf.Ticker", _boom)

    with pytest.raises(YahooFundamentalsError):
        YahooFundamentalsClient().fetch_fundamentals("RELIANCE.NS")
