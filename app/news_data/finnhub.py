from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx

from ..provider_contracts import CAPABILITY_NEWS_EVENT_DATA
from .yahoo import RawNewsItem


class FinnhubError(RuntimeError):
    """Raised when Finnhub cannot provide usable news data."""


class FinnhubCredentialsError(FinnhubError):
    """Raised when no API key is configured -- never silently falls
    back to an unauthenticated or fabricated request."""


class FinnhubNewsClient:
    """A second, independent news adapter (EPIC-M1.91: "at least three
    [implementation paths] where practical") alongside M1.73's
    `YahooNewsClient`. Real and callable in production against
    Finnhub's free-tier `company-news` endpoint; requires an API key,
    read once at construction time. Unit tests never hit the network,
    they monkeypatch the underlying HTTP call with local fixtures.
    """

    source = "finnhub"
    capability = CAPABILITY_NEWS_EVENT_DATA
    version = "1"

    def __init__(self, api_key: str, lookback_days: int = 7, timeout: float = 30.0) -> None:
        if not api_key:
            raise FinnhubCredentialsError("Finnhub API key is required")
        self.api_key = api_key
        self.lookback_days = lookback_days
        self.timeout = timeout

    def fetch_news(self, symbol: str) -> tuple[RawNewsItem, ...]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")

        today: date = datetime.now(timezone.utc).date()
        from_date = today - timedelta(days=self.lookback_days)

        try:
            response = httpx.get(
                "https://finnhub.io/api/v1/company-news",
                params={
                    "symbol": normalized_symbol,
                    "from": from_date.isoformat(),
                    "to": today.isoformat(),
                    "token": self.api_key,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise FinnhubError(f"Finnhub company-news request failed for {normalized_symbol}: {exc}") from exc

        items = []
        for raw in payload or []:
            if not isinstance(raw, dict):
                continue
            external_id = raw.get("id")
            headline = raw.get("headline")
            epoch_seconds = raw.get("datetime")
            if external_id is None or not headline or epoch_seconds is None:
                continue
            try:
                published_at = datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc)
            except (OverflowError, OSError, ValueError, TypeError):
                continue
            items.append(RawNewsItem(external_id=str(external_id), headline=str(headline), published_at=published_at))
        return tuple(items)
