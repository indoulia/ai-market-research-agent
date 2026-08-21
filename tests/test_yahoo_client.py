from datetime import date

import pandas as pd
import pytest

from app.market_data import YahooFinanceClient


def test_yahoo_client_normalizes_and_filters_rows(monkeypatch):
    frame = pd.DataFrame(
        [
            [10, 12, 9, 11, 100],
            [10, 8, 9, 9, 100],
            [10, 12, 9, 11, -1],
            [10, 12, 9, 11, 200],
        ],
        index=pd.to_datetime(["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-01"]),
        columns=["Open", "High", "Low", "Close", "Volume"],
    )
    monkeypatch.setattr("app.market_data.yahoo.yf.download", lambda *args, **kwargs: frame)

    candles = YahooFinanceClient().fetch_daily_candles(" reliance.ns ", date(2026, 8, 1), date(2026, 8, 3))

    assert candles == [["2026-08-01T00:00:00+05:30", 10.0, 12.0, 9.0, 11.0, 200]]


def test_yahoo_client_filters_duplicate_and_invalid_fixture(monkeypatch):
    fixture = pd.DataFrame(
        {"Open": [10, 11, 11, 0], "High": [12, 12, 12, 1], "Low": [9, 10, 10, 0],
         "Close": [11, 11, 11, 1], "Volume": [100, 200, 200, 100]},
        index=pd.to_datetime(["2026-08-03", "2026-08-04", "2026-08-04", "2026-08-05"]),
    )
    monkeypatch.setattr("app.market_data.yahoo.yf.download", lambda *args, **kwargs: fixture)

    candles = YahooFinanceClient().fetch_daily_candles("reliance.ns", date(2026, 8, 3), date(2026, 8, 5))

    assert [(row[1], row[5]) for row in candles] == [(10.0, 100), (11.0, 200)]


def test_yahoo_client_rejects_reverse_range():
    with pytest.raises(ValueError, match="from_date"):
        YahooFinanceClient().fetch_daily_candles("TCS.NS", date(2026, 8, 2), date(2026, 8, 1))


def test_yahoo_client_stamps_daily_bars_at_nse_local_midnight(monkeypatch):
    # EPIC-M1.149: app/scan.py's cutoff/staleness math and the market-data
    # quality validator both require daily bars stamped at midnight in
    # Asia/Kolkata -- a UTC-midnight stamp (this client's previous behavior)
    # makes every Yahoo-ingested row look permanently stale to the scan.
    frame = pd.DataFrame(
        [[10, 12, 9, 11, 100]],
        index=pd.to_datetime(["2026-08-20"]),
        columns=["Open", "High", "Low", "Close", "Volume"],
    )
    monkeypatch.setattr("app.market_data.yahoo.yf.download", lambda *args, **kwargs: frame)

    candles = YahooFinanceClient().fetch_daily_candles("RELIANCE.NS", date(2026, 8, 20), date(2026, 8, 20))

    assert candles == [["2026-08-20T00:00:00+05:30", 10.0, 12.0, 9.0, 11.0, 100]]
