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

TIMELINE_REASON_INITIAL_PREDICTION = "INITIAL_PREDICTION"


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
    evidenceFreshness: str


class TimelineItem(BaseModel):
    """EPIC-M3.4: full, ordered prediction-version timeline -- the
    original prediction plus every immutable revision, each carrying its
    own reason and the specific metrics it changed. Distinct from
    `/history` (paginated, revisions-only) by always including version 1
    (the original) so a caller can reconstruct the *entire* lifecycle in
    one call, not just what changed after it."""

    version: int
    timestamp: datetime
    reason: str
    changeSummary: str
    affectedMetrics: list[str]
    price: Decimal
    targetPrice: Decimal
    stopLoss: Decimal
    probability: Decimal
    score: Decimal | None
    confidence: Decimal
    trustScore: Decimal | None


class EvidenceResponse(BaseModel):
    """EPIC-M3.4: the fundamental/technical/market/news/event evidence
    sections plus provider provenance, as their own contract -- the same
    values already embedded in `RecommendationDetail`, projected out so a
    caller only interested in evidence doesn't have to fetch the full
    detail payload."""

    fundamental: str | None
    technical: str | None
    market: str | None
    news: str | None
    events: str | None
    evidenceStrength: str | None
    liquidity: str
    providerEvidence: list[str]


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
