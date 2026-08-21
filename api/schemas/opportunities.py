"""DTOs for GET /api/v1/opportunities (EPIC-M3.3).

Items reuse M1.135's ``RecommendationSummary`` unchanged -- the epic's own
wording ("same canonical recommendation summary contract as M3.2") and
M3.2's listed minimum fields (symbol, name, price, targetPrice, stopLoss,
horizon, upsidePercent, score, confidence, trustScore, status, updatedAt)
are all already present on that DTO, so a second, parallel item shape
would only create a contract to keep in sync for no benefit.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from .recommendations import RecommendationSummary


class OpportunityFilters(BaseModel):
    """Echoes back exactly the filters/sort this response was computed
    with (AC: filter combinations are server-side and deterministic --
    a client should never have to guess what was actually applied)."""

    market: str | None = None
    horizon: int | None = None
    sector: str | None = None
    industry: str | None = None
    marketCap: str | None = None
    minTrust: Decimal | None = None
    minScore: Decimal | None = None
    minUpside: Decimal | None = None
    liquidityBucket: str | None = None
    status: str | None = None
    search: str | None = None
    sort: str


class OpportunityListResponse(BaseModel):
    items: list[RecommendationSummary]
    page: int
    pageSize: int
    total: int
    asOf: datetime | None
    filters: OpportunityFilters
