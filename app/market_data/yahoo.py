from __future__ import annotations

from datetime import date, datetime, time, timedelta
import math
from typing import Any

import pandas as pd
import yfinance as yf

from .quality import NSE_TIMEZONE


class YahooFinanceError(RuntimeError):
    """Raised when Yahoo Finance cannot provide usable research data."""


class YahooFinanceClient:
    """Daily NSE adapter. Yahoo Finance is suitable for research, not redistribution."""

    source = "yahoo-finance"
    capability = "MARKET_DATA"
    version = "1"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def fetch_daily_candles(self, symbol: str, from_date: date, to_date: date) -> list[list[Any]]:
        if from_date > to_date:
            raise ValueError("from_date must be on or before to_date")
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")
        try:
            frame = yf.download(
                normalized_symbol,
                start=from_date.isoformat(),
                end=(to_date + timedelta(days=1)).isoformat(),
                interval="1d",
                auto_adjust=False,
                progress=False,
                group_by="column",
                threads=False,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise YahooFinanceError(f"Yahoo Finance history request failed for {normalized_symbol}: {exc}") from exc
        if frame is None or frame.empty:
            return []
        return self._normalize(frame, from_date, to_date)

    @staticmethod
    def _normalize(frame: pd.DataFrame, from_date: date, to_date: date) -> list[list[Any]]:
        if isinstance(frame.columns, pd.MultiIndex):
            ticker = frame.columns.get_level_values(-1)[0]
            frame = frame.xs(ticker, axis=1, level=-1)
        required = {"Open", "High", "Low", "Close", "Volume"}
        if not required.issubset(frame.columns):
            raise YahooFinanceError("Yahoo Finance response is missing OHLCV columns")

        rows: dict[str, list[Any]] = {}
        for timestamp, values in frame.sort_index().iterrows():
            try:
                numbers = [float(values[column]) for column in ("Open", "High", "Low", "Close", "Volume")]
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            open_price, high, low, close, volume = numbers
            if (
                not all(math.isfinite(value) for value in numbers)
                or min(open_price, high, low, close) <= 0
                or volume < 0
                or high < max(open_price, close)
                or low > min(open_price, close)
            ):
                continue
            stamp = pd.Timestamp(timestamp).to_pydatetime()
            # yfinance daily bars index by exchange trading date with no
            # meaningful intraday time; every other daily-bar producer/consumer
            # in this repo (app/scan.py's cutoff math, the market-data quality
            # validator, every test fixture) stamps/expects that date at
            # midnight in Asia/Kolkata -- anchoring to UTC midnight instead
            # (as this used to) shifts the same calendar date across the IST
            # boundary and makes every Yahoo-ingested row look permanently
            # stale to the discovery scan (EPIC-M1.149).
            trading_date = stamp.date() if stamp.tzinfo is None else stamp.astimezone(NSE_TIMEZONE).date()
            if not from_date <= trading_date <= to_date:
                continue
            localized = datetime.combine(trading_date, time.min, tzinfo=NSE_TIMEZONE)
            rows[trading_date.isoformat()] = [localized.isoformat(), open_price, high, low, close, int(volume)]
        return [rows[key] for key in sorted(rows)]
