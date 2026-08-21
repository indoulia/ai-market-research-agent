"""DTOs for GET /api/v1/predictions/active[/{predictionId}] (EPIC-M3.8).

Deliberately compact ("a compact live view", per the EPIC's own Objective)
-- unlike `RecommendationSummary`/`RecommendationDetail` (EPIC-M1.135/137)
this contract does not repeat fundamental/news/event narrative summaries,
the full `PredictionVersions` block, or `upsidePct`/`probability`; a caller
that needs those already has `/recommendations` and `/recommendations/{id}`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ActivePrediction(BaseModel):
    predictionId: int
    symbol: str
    companyName: str | None
    exchange: str
    price: Decimal | None
    targetPrice: Decimal
    stopLoss: Decimal
    horizon: int
    remainingTradingDays: int | None
    distanceToTargetPercent: Decimal | None
    distanceToStopLossPercent: Decimal | None
    score: Decimal | None
    confidence: Decimal
    trustScore: Decimal | None
    status: str
    lastPriceAt: datetime | None
    lastRevisionAt: datetime | None
    nextEvaluationAt: datetime | None
