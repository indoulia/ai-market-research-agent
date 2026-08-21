"""DTOs for GET /api/v1/dashboard/snapshot (EPIC-M3.2).

This is a read-side *composition* over already-merged, already-tested
query services -- ``api/services/recommendations.py`` (M1.135),
``api/services/market.py`` (M1.139), ``api/services/news_events.py``
(M1.139) and ``api/services/tracking.py`` (M1.147). No new business/
ranking/aggregation logic is introduced here beyond field renaming and
merging two already-sorted feeds into one, matching the EPIC's own
"no UI-side business ranking" precedent from M1.135.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from .market import IndexQuote

DASHBOARD_EVENT_NEWS = "NEWS"
DASHBOARD_EVENT_CORPORATE_ACTION = "CORPORATE_ACTION"


class DashboardOpportunity(BaseModel):
    """One top-opportunity summary card, per EPIC-M3.2's API Contract field
    list. A deliberately leaner projection of M1.135's `RecommendationSummary`
    -- only the fields the EPIC names, plus `id` -- not a second, divergent
    recommendation representation (the underlying row is the exact same one
    `/recommendations` returns). `id` is the one addition beyond the EPIC's
    own "must expose at minimum" list: the Acceptance Criteria requires
    "navigation into full opportunity/detail views", which is impossible
    without an identifier for the existing `/recommendation/:id` detail
    route -- an honest, necessary extension, not a contract violation
    ("at minimum" permits additional fields)."""

    id: int
    symbol: str
    name: str
    price: Decimal | None
    targetPrice: Decimal
    stopLoss: Decimal
    horizon: int
    upsidePercent: Decimal
    score: Decimal
    confidence: Decimal
    trustScore: Decimal | None
    status: str
    updatedAt: datetime


class DashboardEvent(BaseModel):
    """One entry in the important-events strip -- a merged, time-ordered
    projection of M1.139's `/news` and `/events` feeds (the same merge
    the Flutter M1.140 UI already does client-side, done once here
    server-side so the dashboard needs only one request)."""

    kind: str
    symbol: str
    title: str
    occurredAt: datetime
    source: str
    materiality: str | None
    evidenceId: int


class DashboardTrustSummary(BaseModel):
    """A compact projection of M1.147's `/tracking/summary` -- only the
    fields relevant to a one-glance trust widget. Not a recomputation:
    every value here is read verbatim from `TrackingSummary`."""

    trustScore: Decimal | None
    trustDelta: Decimal | None
    calibrationScore: Decimal | None
    sampleSize: int
    smallSample: bool
    modelVersion: str | None


class DataFreshness(BaseModel):
    """Per-section as-of timestamps so a viewer can tell which parts of the
    snapshot are current vs. stale, without fabricating a single combined
    number across sources that update on different cadences."""

    opportunitiesAsOf: datetime | None
    marketAsOf: datetime
    newsAsOf: datetime | None


class DashboardSnapshot(BaseModel):
    marketStatus: str
    asOf: datetime
    marketRegime: str | None
    indices: list[IndexQuote]
    topOpportunities: list[DashboardOpportunity]
    importantEvents: list[DashboardEvent]
    recentChanges: list[DashboardOpportunity]
    trustSummary: DashboardTrustSummary
    dataFreshness: DataFreshness
