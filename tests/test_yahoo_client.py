from datetime import date

import pandas as pd

from app.market_data import YahooFinanceClient


def test_yahoo_client_normalizes_and_filters_fixture_rows():
    index = pd.to_datetime(["2026-08-18", "2026-08-19", "2026-08-19", "2026-08-20"])
    frame = pd.DataFrame({"Open": [10, 20, 20, 0], "High": [11, 21, 21, 1],
                          "Low": [9, 18, 19, 0], "Close": [10.5, 19, 20, 1],
                          "Volume": [100, 100, 100, 100]}, index=index)
    candles = YahooFinanceClient(lambda *args, **kwargs: frame).fetch_daily_candles(
        " reliance.ns ", date(2026, 8, 1), date(2026, 8, 20))
    assert candles == [["2026-08-18T00:00:00", 10.0, 11.0, 9.0, 10.5, 100],
                       ["2026-08-19T00:00:00", 20.0, 21.0, 18.0, 19.0, 100]]


def test_yahoo_client_empty_fixture_is_valid():
    frame = pd.DataFrame()
    assert YahooFinanceClient(lambda *args, **kwargs: frame).fetch_daily_candles(
        "TCS.NS", date(2026, 8, 1), date(2026, 8, 2)) == []
