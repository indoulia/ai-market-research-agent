from datetime import date

import pandas as pd
import pytest

from app.market_data import YahooFinanceClient


def test_yahoo_client_normalizes_and_filters_rows(monkeypatch):
    frame = pd.DataFrame(
        [
            [10, 12, 9, 11, 100],
            [10, 8, 9, 9, 100],       # invalid OHLC
            [10, 12, 9, 11, -1],      # invalid volume
            [10, 12, 9, 11, 200],     # duplicate date; last valid row wins
        ],
        index=pd.to_datetime(["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-01"]),
        columns=["Open", "High", "Low", "Close", "Volume"],
    )
    monkeypatch.setattr("app.market_data.yahoo.yf.download", lambda *args, **kwargs: frame)

    candles = YahooFinanceClient().fetch_daily_candles(" reliance.ns ", date(2026, 8, 1), date(2026, 8, 3))

    assert candles == [["2026-08-01T00:00:00+00:00", 10.0, 12.0, 9.0, 11.0, 200]]


def test_yahoo_client_rejects_reverse_range():
    with pytest.raises(ValueError, match="from_date"):
        YahooFinanceClient().fetch_daily_candles("TCS.NS", date(2026, 8, 2), date(2026, 8, 1))
