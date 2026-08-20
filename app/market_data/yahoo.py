from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import math
from typing import Any

import yfinance as yf


class YahooFinanceError(RuntimeError):
    """Raised when Yahoo Finance cannot provide usable research data."""


class YahooFinanceClient:
    """Daily NSE adapter. Yahoo Finance is suitable for research, not redistribution."""

    source = "yahoo-finance"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def fetch_daily_candles(self, symbol: str, from_date: date, to_date: date) -> list[list[Any]]:
        if from_date > to_date:
            raise ValueError("from_date must be on or before to_date")
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        try:
            frame = yf.download(
                symbol, start=from_date.isoformat(),
                end=(to_date + timedelta(days=1)).isoformat(),
                auto_adjust=False, progress=False, group_by="column", threads=False,
            )
        except Exception as exc:
            raise YahooFinanceError(f"Yahoo Finance history request failed: {exc}") from exc
        if frame is None or frame.empty:
            return []
        rows: dict[str, list[Any]] = {}
        for timestamp, values in frame.iterrows():
            try:
                fields = [values[column] for column in ("Open", "High", "Low", "Close", "Volume")]
            except (KeyError, TypeError):
                # yfinance may return a ticker-level MultiIndex for a single symbol.
                try:
                    fields = [values[(column, symbol)] for column in ("Open", "High", "Low", "Close", "Volume")]
                except (KeyError, TypeError):
                    continue
            numbers = [float(value) for value in fields]
            open_price, high, low, close, volume = numbers
            if (not all(math.isfinite(value) for value in numbers)
                    or min(open_price, high, low, close) <= 0
                    or volume < 0
                    or high < max(open_price, close)
                    or low > min(open_price, close)):
                continue
            stamp = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp
            if stamp.tzinfo is None:
                stamp = datetime.combine(stamp.date(), time(), tzinfo=timezone.utc)
            else:
                stamp = stamp.astimezone(timezone.utc)
            key = stamp.date().isoformat()
            rows[key] = [stamp.isoformat(), open_price, high, low, close, int(volume)]
        return [rows[key] for key in sorted(rows)]
