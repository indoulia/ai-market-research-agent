"""DTOs for GET /api/v1/discoveries (EPIC-M1.139) and GET /api/v1/discovery/*
(EPIC-M3.6 discovery intelligence: summary, history, candidates)."""

from __future__ import annotations

from datetime import date, datetime
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


# EPIC-M3.6: candidate lifecycle stage vocabulary. "ANALYZED" is
# deliberately not a member here -- this pipeline's consensus decision
# (app/recommendation_generator.py) is synchronous with discovery routing,
# so there is no persisted resting state between "discovered" and
# "qualified/suppressed" for a single candidate to occupy. "Analyzed" is
# still an honest, meaningful *funnel count* (see `DiscoveryFunnelCounts`
# below) -- it is just never a candidate's own current stage.
LIFECYCLE_DISCOVERED = "DISCOVERED"
LIFECYCLE_QUALIFIED = "QUALIFIED"
LIFECYCLE_SUPPRESSED = "SUPPRESSED"
LIFECYCLE_PUBLISHED = "PUBLISHED"


class DiscoveryCandidate(BaseModel):
    """One row of `GET /api/v1/discovery/candidates` -- the same discovery
    universe as `DiscoveryItem` above, reprojected with an explicit
    lifecycle stage and (only for an authenticated caller) a suppression
    reason, per EPIC-M3.6. Suppressed is never a negative/bearish call --
    it only means this candidate did not clear the positive-opportunity
    bar this cycle.

    `candidateId` is the underlying `DiscoveryRecord.id` (EPIC-M3.6's own
    field name for it). The EPIC's `providerEvidence` and `qualification`
    fields are deliberately not separate keys here -- they are already
    served, without inventing a second representation, by
    `discoveryReasons` (the provider's own rationale text) and
    `score`/`trustScore` (the qualification signal) respectively.
    `publishedRecommendationId` is only set once `lifecycleStage` reaches
    `PUBLISHED`, letting a client link straight to `/recommendation/:id`."""

    candidateId: int
    symbol: str
    companyName: str | None
    exchange: str
    sector: str
    industry: str
    marketCapBucket: str
    liquidity: str
    discoveredAt: datetime
    discoverySources: list[str]
    discoveryReasons: list[str]
    score: Decimal | None
    trustScore: Decimal | None
    lifecycleStage: str
    suppressionReason: str | None = None
    publishedRecommendationId: int | None = None


class DiscoveryFunnelCounts(BaseModel):
    discovered: int
    analyzed: int
    qualified: int
    suppressed: int
    published: int


class DiscoverySourceEffectiveness(BaseModel):
    """Per-source discovery effectiveness, reprojected verbatim from
    EPIC-M1.28's `app.discovery_effectiveness.DiscoverySourceFunnel` --
    no new scoring/verdict logic, just camelCase field names for the API."""

    source: str
    discoveredCount: int
    analyzedCount: int
    rejectedCount: int
    qualifiedCount: int
    evaluatedCount: int
    successCount: int
    failureCount: int
    unevaluableCount: int
    openCount: int
    successRate: Decimal | None
    verdict: str


class DiscoverySummary(BaseModel):
    asOf: datetime
    counts: DiscoveryFunnelCounts
    effectivenessBySource: list[DiscoverySourceEffectiveness]
    effectivenessReportVersion: str


class DiscoveryHistoryPoint(BaseModel):
    scanDate: date
    discoveredCount: int
    analyzedCount: int
    qualifiedCount: int
    suppressedCount: int
    publishedCount: int
