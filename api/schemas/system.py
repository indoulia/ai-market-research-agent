"""DTOs for GET /api/v1/system/{health,providers,data-freshness,events}
(EPIC-M3.11).

Composes, rather than reinvents, the already-merged provider-reliability
and freshness machinery: `app.provider_quality` (M1.93), `app.
provider_outage_tracker` (M1.114) and `app.refresh_policy` (M1.35). Field
names follow this EPIC's own "Provider response" contract list exactly
(`providerId`, `capability`, `status`, `lastSuccessAt`, `latencyMs`,
`freshness`, `failureRate`, `fallbackActive`, `qualityScore`); `capability`
is realized as the underlying `data_type` string (`MARKET_DATA`/
`NEWS_EVENT`/`FUNDAMENTAL_DATA`) -- the real, already-shipped segmentation
key `ProviderQualityMetric` groups by -- rather than a separate, unused
`provider_contracts.ALL_CAPABILITIES` vocabulary that no fetch-attempt
row actually carries.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

SYSTEM_STATUS_OK = "OK"
SYSTEM_STATUS_DEGRADED = "DEGRADED"
SYSTEM_STATUS_OUTAGE = "OUTAGE"


class Freshness(BaseModel):
    """How stale the newest successful fetch is against M1.35's own
    `FRESHNESS_POLICY` threshold for this capability -- never a fabricated
    single number across capabilities with different real cadences."""

    ageSeconds: int | None
    thresholdSeconds: int
    isFresh: bool


class ProviderStatus(BaseModel):
    providerId: str
    capability: str
    status: str
    lastSuccessAt: datetime | None
    latencyMs: int | None
    freshness: Freshness
    failureRate: Decimal | None
    fallbackActive: bool
    qualityScore: Decimal | None


class SystemHealthResponse(BaseModel):
    status: str
    checkedAt: datetime
    apiVersion: str
    databaseOk: bool
    providerStatusCounts: dict[str, int]
    activeOutageCount: int
    marketSession: str


class DataFreshnessItem(BaseModel):
    capability: str
    lastSuccessAt: datetime | None
    ageSeconds: int | None
    thresholdSeconds: int
    isFresh: bool


class SystemEventItem(BaseModel):
    id: str
    type: str
    severity: str
    capability: str | None
    exchange: str | None
    description: str
    occurredAt: datetime
