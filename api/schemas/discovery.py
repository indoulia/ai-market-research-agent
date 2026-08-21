"""DTOs for GET /api/v1/discoveries (EPIC-M1.139)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

STATUS_PENDING_ANALYSIS = "PENDING_ANALYSIS"


class DiscoveryItem(BaseModel):
    symbol: str
    companyName: str | None
    exchange: str
    sector: str
    industry: str
    marketCapBucket: str
    liquidity: str
    discoveredAt: datetime
    discoveryReasons: list[str]
    score: Decimal | None
    trustScore: Decimal | None
    eligibility: bool | None
    status: str
