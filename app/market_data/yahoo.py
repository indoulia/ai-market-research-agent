from __future__ import annotations

from datetime import date
from typing import Any, Callable


class YahooFinanceError(RuntimeError):
    """Raised when Yahoo Finance returns unusable research data."""


class YahooFinanceClient:
    """Yahoo daily NSE adapter; returns the existing six-field candle contract."""

    def __init__(self, downloader: Callable[..., Any] | None = None) -> None:
        self._downloader = downloader

    def fetch_daily_candles(self, symbol: str, from_date: date, to_date: date) -> list[list[Any]]:
        if from_date > to_date:
            raise ValueError("from_date must be on or before to_date")
        downloader = self._downloader
        if downloader is None:
            import yfinance
            downloader = yfinance.download
        try:
            frame = downloader(symbol.strip().upper(), start=from_date, end=to_date, interval="1d",
                               auto_adjust=False, progress=False, group_by="column")
        except Exception as exc:
            raise YahooFinanceError(f"Yahoo historical download failed for {symbol}: {exc}") from exc
        if frame is None or frame.empty:
            return []
        rows: list[list[Any]] = []
        seen: set[str] = set()
        for timestamp, row in frame.iterrows():
            key = timestamp.isoformat()
            if key in seen:
                continue
            seen.add(key)
            values = [row.get(field) for field in ("Open", "High", "Low", "Close", "Volume")]
            if any(value is None or value != value for value in values):
                continue
            open_price, high, low, close, volume = values
            if min(open_price, high, low, close) <= 0 or volume < 0 or high < max(open_price, close) or low > min(open_price, close):
                continue
            rows.append([key, float(open_price), float(high), float(low), float(close), int(volume)])
        return rows
