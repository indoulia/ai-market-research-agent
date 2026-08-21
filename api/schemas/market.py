"""DTOs for GET /api/v1/market/summary (EPIC-M1.139)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

MARKET_STATUS_UNKNOWN = "UNKNOWN"
"""No market-calendar/session module exists yet (EPIC-M1.121, not
implemented) -- this platform cannot honestly claim to know whether the
market is currently open, so `marketStatus` is always this value until
M1.121 lands, never guessed from wall-clock time."""


class SectorMove(BaseModel):
    sector: str
    averageChangePct: Decimal


class IndexQuote(BaseModel):
    """Shape reserved for future index-level data. Always empty for now --
    this platform ingests individual NSE equity prices only, no index
    (e.g. NIFTY50) feed exists, so fabricating a value here would be
    dishonest rather than merely incomplete."""

    name: str
    value: Decimal
    changePct: Decimal


class MarketSummary(BaseModel):
    asOf: datetime
    marketStatus: str
    regime: str | None
    advanceDecline: Decimal | None
    volume: int | None
    volatility: Decimal | None
    indexes: list[IndexQuote]
    sectorLeaders: list[SectorMove]
    sectorLaggards: list[SectorMove]
