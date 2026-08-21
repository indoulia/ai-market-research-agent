from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import yfinance as yf


class YahooFundamentalsError(RuntimeError):
    """Raised when Yahoo Finance cannot provide usable fundamentals data."""


@dataclass(frozen=True)
class RawFundamentals:
    """Whatever fields the provider actually returned for one instrument,
    at the moment it was fetched -- every field is independently optional
    (scope: "ingest ... where available"), never fabricated when the
    provider itself does not report it."""

    period_end_date: date | None
    revenue: Decimal | None
    net_income: Decimal | None
    eps: Decimal | None
    gross_margin: Decimal | None
    operating_margin: Decimal | None
    net_margin: Decimal | None
    debt_to_equity: Decimal | None
    free_cash_flow: Decimal | None
    pe_ratio: Decimal | None
    price_to_book: Decimal | None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _period_end_date(info: dict) -> date | None:
    epoch_seconds = info.get("mostRecentQuarter")
    if epoch_seconds is None:
        return None
    try:
        return datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc).date()
    except (OverflowError, OSError, ValueError, TypeError):
        return None


class YahooFundamentalsClient:
    """Company-fundamentals adapter mirroring `app.market_data.YahooFinanceClient`'s
    own boundary: Yahoo Finance is suitable for research, not licensed
    redistribution. Real and callable in production; unit tests never hit
    the network, they monkeypatch `yf.Ticker` with local fixtures (the
    same pattern `test_yahoo_client.py` already established for price
    data)."""

    source = "yahoo-finance"
    capability = "FUNDAMENTAL_DATA"
    version = "1"

    def fetch_fundamentals(self, symbol: str) -> RawFundamentals | None:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")
        try:
            info = yf.Ticker(normalized_symbol).info
        except Exception as exc:
            raise YahooFundamentalsError(f"Yahoo Finance fundamentals request failed for {normalized_symbol}: {exc}") from exc

        if not info:
            return None

        return RawFundamentals(
            period_end_date=_period_end_date(info),
            revenue=_decimal(info.get("totalRevenue")),
            net_income=_decimal(info.get("netIncomeToCommon")),
            eps=_decimal(info.get("trailingEps")),
            gross_margin=_decimal(info.get("grossMargins")),
            operating_margin=_decimal(info.get("operatingMargins")),
            net_margin=_decimal(info.get("profitMargins")),
            debt_to_equity=_decimal(info.get("debtToEquity")),
            free_cash_flow=_decimal(info.get("freeCashflow")),
            pe_ratio=_decimal(info.get("trailingPE")),
            price_to_book=_decimal(info.get("priceToBook")),
        )
