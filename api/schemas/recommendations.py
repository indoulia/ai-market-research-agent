"""DTOs for GET /api/v1/recommendations (EPIC-M1.135)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

RECOMMENDATION_LABEL = "POSITIVE_OPPORTUNITY"
"""The only recommendation category this platform ever emits (product
constraint: positive-opportunity recommendations only, never sell/bearish)."""

EVIDENCE_FRESH = "FRESH"
EVIDENCE_STALE = "STALE"
EVIDENCE_UNKNOWN = "UNKNOWN"


class PredictionVersions(BaseModel):
    """Every version tag needed to replay how this recommendation was produced."""

    modelVersion: str
    featureVersion: str
    consensusContractVersion: str
    horizonSelectionVersion: str
    scoringContractVersion: str
    rankingVersion: str | None


class RecommendationSummary(BaseModel):
    id: int
    symbol: str
    exchange: str
    companyName: str | None
    asOf: datetime
    price: Decimal | None
    changePct: Decimal | None
    recommendation: str
    horizonDays: int
    targetPrice: Decimal
    stopLoss: Decimal
    upsidePct: Decimal
    probability: Decimal
    score: Decimal
    confidence: Decimal
    trustScore: Decimal | None
    uncertaintyLevel: str | None
    fundamentalSummary: str | None
    newsSummary: str | None
    eventSummary: str | None
    marketSummary: str | None
    evidenceFreshness: str
    status: str
    predictionVersion: PredictionVersions
    updatedAt: datetime
