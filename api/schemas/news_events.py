"""DTOs for GET /api/v1/news and GET /api/v1/events (EPIC-M1.139)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NewsItem(BaseModel):
    symbol: str
    headline: str
    source: str
    publishedAt: datetime
    detectedAt: datetime
    materiality: str
    affectedSecurities: list[str]
    evidenceId: int


class EventItem(BaseModel):
    symbol: str
    type: str
    title: str
    effectiveAt: datetime
    detectedAt: datetime
    materiality: str | None
    source: str
    evidenceId: int
