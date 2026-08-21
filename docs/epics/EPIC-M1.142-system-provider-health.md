# EPIC-M1.142 — System & Provider Health

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Provide a compact operational view of MRA data/provider health, freshness, latency and fallback state so users can distinguish a market condition from an information-system degradation.

## UI Scope
- Provider status grid.
- Data freshness by capability.
- Last successful fetch.
- Latency indicator.
- Degraded/fallback state.
- Provider quality/cost summary where appropriate.
- Market-calendar/session status.
- System incident/history drill-down.

## API Contract
`GET /api/v1/system/health`
`GET /api/v1/system/providers`
`GET /api/v1/system/data-freshness`
`GET /api/v1/system/events`

Provider response:
`providerId`, `capability`, `status`, `lastSuccessAt`, `latencyMs`, `freshness`, `failureRate`, `fallbackActive`, `qualityScore`.

## Acceptance Criteria
- Health state is read-only to normal users.
- Provider outages and stale data are visible.
- UI never exposes secrets or provider credentials.
- Health information reconciles with M1.93, M1.118 and M1.126.
