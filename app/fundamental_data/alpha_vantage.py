from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ..provider_contracts import CAPABILITY_FUNDAMENTAL_DATA
from .yahoo import RawFundamentals


class AlphaVantageError(RuntimeError):
    """Raised when Alpha Vantage cannot provide usable fundamentals data."""


class AlphaVantageCredentialsError(AlphaVantageError):
    """Raised when no API key is configured -- never silently falls
    back to an unauthenticated or fabricated request."""


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "None", ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _period_end_date(value: Any):
    if not value or value == "None":
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


class AlphaVantageFundamentalsClient:
    """A second, independent fundamentals adapter (EPIC-M1.91: "at least
    three [implementation paths] where practical") alongside M1.72's
    `YahooFundamentalsClient`. Real and callable in production against
    Alpha Vantage's free-tier `OVERVIEW` endpoint; requires an API key
    (`api_key`), read once at construction time -- never a fabricated or
    unauthenticated request. Unit tests never hit the network, they
    monkeypatch the underlying HTTP call with local fixtures.
    """

    source = "alpha-vantage"
    capability = CAPABILITY_FUNDAMENTAL_DATA
    version = "1"

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise AlphaVantageCredentialsError("Alpha Vantage API key is required")
        self.api_key = api_key
        self.timeout = timeout

    def fetch_fundamentals(self, symbol: str) -> RawFundamentals | None:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")

        try:
            response = httpx.get(
                "https://www.alphavantage.co/query",
                params={"function": "OVERVIEW", "symbol": normalized_symbol, "apikey": self.api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise AlphaVantageError(f"Alpha Vantage overview request failed for {normalized_symbol}: {exc}") from exc

        if not payload or "Symbol" not in payload:
            return None

        gross_margin = None
        revenue = _decimal(payload.get("RevenueTTM"))
        gross_profit = _decimal(payload.get("GrossProfitTTM"))
        if revenue is not None and gross_profit is not None and revenue != 0:
            gross_margin = gross_profit / revenue

        return RawFundamentals(
            period_end_date=_period_end_date(payload.get("LatestQuarter")),
            revenue=revenue,
            net_income=None,
            eps=_decimal(payload.get("EPS")),
            gross_margin=gross_margin,
            operating_margin=_decimal(payload.get("OperatingMarginTTM")),
            net_margin=_decimal(payload.get("ProfitMargin")),
            debt_to_equity=None,
            free_cash_flow=None,
            pe_ratio=_decimal(payload.get("PERatio")),
            price_to_book=_decimal(payload.get("PriceToBookRatio")),
        )
