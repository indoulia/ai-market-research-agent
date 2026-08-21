"""DTOs for GET /api/v1/tracking/* (EPIC-M1.147)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

VALID_RANGES = ("7d", "30d", "90d", "1y")
VALID_TIMESERIES_METRICS = ("trust", "hitRate", "return", "calibration")
VALID_BUCKETS = ("day", "week")
VALID_BREAKDOWN_DIMENSIONS = ("horizon", "sector", "marketCap", "regime", "setup")
VALID_PREDICTION_STATUSES = ("active", "closed")

MODEL_VERSION_MIXED = "MIXED"


class TrackingSummary(BaseModel):
    range: str
    predictionCount: int
    closedCount: int
    targetHitRate: Decimal | None
    stopLossRate: Decimal | None
    horizonExpiryRate: Decimal | None
    avgRealizedReturn: Decimal | None
    avgPredictedReturn: Decimal | None
    calibrationScore: Decimal | None
    trustScore: Decimal | None
    trustDelta: Decimal | None
    modelVersion: str | None
    benchmarkReturn: Decimal | None
    relativeReturn: Decimal | None
    smallSample: bool


class TimeseriesPoint(BaseModel):
    bucketStart: datetime
    value: Decimal | None
    sampleCount: int


class TimeseriesResponse(BaseModel):
    metric: str
    range: str
    bucket: str
    points: list[TimeseriesPoint]


class BreakdownItem(BaseModel):
    key: str
    predictionCount: int
    closedCount: int
    targetHitRate: Decimal | None
    avgRealizedReturn: Decimal | None
    smallSample: bool


class BreakdownResponse(BaseModel):
    dimension: str
    items: list[BreakdownItem]


class TrackedPrediction(BaseModel):
    id: int
    symbol: str
    status: str
    asOf: datetime
    horizonDays: int
    predictedReturn: Decimal
    realizedReturn: Decimal | None
    outcome: str | None
    modelVersion: str
