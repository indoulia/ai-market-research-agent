from __future__ import annotations

from datetime import date, datetime, time, timezone
import csv
import io
from typing import Any

import httpx

from ..provider_contracts import CAPABILITY_MARKET_DATA


class StooqError(RuntimeError):
    """Raised when Stooq cannot provide usable research data."""


class StooqClient:
    """A third, independent, no-authentication market-data adapter for
    NSE daily OHLCV -- proves M1.90's `DailyHistoryProvider` contract is
    genuinely vendor-neutral (EPIC-M1.91: "implement at least three
    providers for each critical capability where practical"). Real and
    callable in production; unit tests never hit the network, they
    monkeypatch the underlying HTTP call with local fixtures, matching
    every other adapter in this platform. Stooq is a free research/
    prototyping source, not a licensed redistribution channel -- the
    same caveat this platform already documents for Yahoo Finance.
    """

    source = "stooq"
    capability = CAPABILITY_MARKET_DATA
    version = "1"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def fetch_daily_candles(self, symbol: str, from_date: date, to_date: date) -> list[list[Any]]:
        if from_date > to_date:
            raise ValueError("from_date must be on or before to_date")
        normalized_symbol = symbol.strip().lower()
        if not normalized_symbol:
            raise ValueError("symbol is required")

        try:
            response = httpx.get(
                "https://stooq.com/q/d/l/",
                params={
                    "s": normalized_symbol,
                    "d1": from_date.strftime("%Y%m%d"),
                    "d2": to_date.strftime("%Y%m%d"),
                    "i": "d",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.text
        except Exception as exc:
            raise StooqError(f"Stooq history request failed for {normalized_symbol}: {exc}") from exc

        return self._normalize(body, from_date, to_date)

    @staticmethod
    def _normalize(body: str, from_date: date, to_date: date) -> list[list[Any]]:
        rows: dict[str, list[Any]] = {}
        reader = csv.DictReader(io.StringIO(body))
        for record in reader:
            try:
                row_date = datetime.strptime(record["Date"], "%Y-%m-%d").date()
                numbers = [float(record[key]) for key in ("Open", "High", "Low", "Close", "Volume")]
            except (KeyError, TypeError, ValueError):
                continue
            open_price, high, low, close, volume = numbers
            if (
                min(open_price, high, low, close) <= 0
                or volume < 0
                or high < max(open_price, close)
                or low > min(open_price, close)
                or not from_date <= row_date <= to_date
            ):
                continue
            stamp = datetime.combine(row_date, time(), tzinfo=timezone.utc)
            rows[row_date.isoformat()] = [stamp.isoformat(), open_price, high, low, close, int(volume)]
        return [rows[key] for key in sorted(rows)]
