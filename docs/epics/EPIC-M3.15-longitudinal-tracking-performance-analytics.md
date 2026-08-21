# EPIC-M3.15 — Longitudinal Tracking & Performance Analytics

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Expose how individual predictions and MRA aggregate performance evolve over time, preserving clean historical evidence and making improvement visible.

## UI Scope
- Prediction outcome history.
- Trust trend.
- Hit/SL/expiry distributions.
- Return and benchmark-relative trend.
- Horizon/sector/regime/size/setup breakdowns.
- Prediction revision timeline.
- Filters and date range.
- Compact charts with exact values available on interaction.

## API Contract
`GET /api/v1/tracking/summary`
`GET /api/v1/tracking/timeseries`
`GET /api/v1/tracking/breakdown`
`GET /api/v1/tracking/predictions`

Query:
`from`, `to`, `horizon`, `sector`, `marketCap`, `regime`, `symbol`, `setup`, `page`, `pageSize`.

Responses include:
`metric`, `value`, `sampleSize`, `asOf`, `methodologyVersion`, `benchmark`, `confidence/reliability` where applicable.

## Acceptance Criteria
- Aggregate metrics reconcile with immutable prediction outcomes.
- Time-series points are reproducible.
- Small samples are identified.
- User can drill from aggregate metric to underlying predictions where permitted.
- Mobile and web charts remain legible and compact.
