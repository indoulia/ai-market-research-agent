from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import yfinance as yf


class YahooNewsError(RuntimeError):
    """Raised when Yahoo Finance cannot provide usable news data."""


@dataclass(frozen=True)
class RawNewsItem:
    external_id: str
    headline: str
    published_at: datetime


def _parse_published_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


class YahooNewsClient:
    """Company news adapter mirroring `app.market_data.YahooFinanceClient`'s
    and `app.fundamental_data.YahooFundamentalsClient`'s own provider
    boundary: real and callable in production via `yf.Ticker(...).news`;
    unit tests never hit the network, they monkeypatch `yf.Ticker` with
    local fixtures.

    Handles both the older flat Yahoo news item shape and the newer
    `{"id": ..., "content": {...}}` shape defensively -- an item missing
    an id, headline, or publish time is skipped rather than fabricated.
    """

    source = "yahoo-finance"
    capability = "NEWS_EVENT_DATA"
    version = "1"

    def fetch_news(self, symbol: str) -> tuple[RawNewsItem, ...]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")
        try:
            raw_items = yf.Ticker(normalized_symbol).news
        except Exception as exc:
            raise YahooNewsError(f"Yahoo Finance news request failed for {normalized_symbol}: {exc}") from exc

        items = []
        for raw in raw_items or []:
            if not isinstance(raw, dict):
                continue
            content = raw.get("content") if isinstance(raw.get("content"), dict) else raw

            external_id = raw.get("id") or content.get("uuid") or raw.get("uuid")
            headline = content.get("title") or raw.get("title")
            published_at = _parse_published_at(content.get("pubDate") or raw.get("providerPublishTime"))

            if not external_id or not headline or published_at is None:
                continue

            items.append(RawNewsItem(external_id=str(external_id), headline=str(headline), published_at=published_at))
        return tuple(items)
