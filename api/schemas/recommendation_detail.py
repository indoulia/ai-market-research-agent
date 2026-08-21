"""DTOs for the /api/v1/recommendations/{id} detail/history/events/outcome
contracts (EPIC-M1.137)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from .recommendations import PredictionVersions

EVENT_TYPE_NEWS = "NEWS"
EVENT_TYPE_CORPORATE_ACTION = "CORPORATE_ACTION"
EVENT_TYPE_REANALYSIS_TRIGGER = "REANALYSIS_TRIGGER"

OUTCOME_STATUS_PENDING = "PENDING"


class RecommendationDetail(BaseModel):
    id: int
    symbol: str
    exchange: str
    companyName: str | None
    predictionVersion: PredictionVersions
    createdAt: datetime
    updatedAt: datetime
    asOf: datetime
    entryPrice: Decimal
    currentPrice: Decimal | None
    targetPrice: Decimal
    stopLoss: Decimal
    horizonDays: int
    expiryAt: datetime | None
    upsidePct: Decimal
    probability: Decimal
    score: Decimal | None
    confidence: Decimal
    trustScore: Decimal | None
    uncertainty: str | None
    evidenceStrength: str | None
    fundamental: str | None
    technical: str | None
    market: str | None
    news: str | None
    events: str | None
    benchmarkRelative: str | None
    liquidity: str
    providerEvidence: list[str]
    status: str


class HistoryItem(BaseModel):
    timestamp: datetime
    version: int
    price: Decimal
    targetPrice: Decimal
    stopLoss: Decimal
    probability: Decimal
    score: Decimal | None
    confidence: Decimal
    trustScore: Decimal | None
    triggerType: str
    triggerEventId: int | None
    changeSummary: str


class EventItem(BaseModel):
    timestamp: datetime
    eventType: str
    description: str
    materiality: str | None


class OutcomeResponse(BaseModel):
    status: str
    detectedAt: datetime | None
    observedPrice: Decimal | None
    realizedReturnPct: Decimal | None
    targetHit: bool | None
    stopLossHit: bool | None
    horizonExpired: bool | None
    benchmarkReturnPct: Decimal | None
    evidenceId: int | None
