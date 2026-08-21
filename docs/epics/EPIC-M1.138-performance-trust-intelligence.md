# EPIC-M1.138 — Performance & Trust Intelligence

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Show whether MRA is actually becoming better over time, with trustworthy performance and calibration metrics rather than vanity accuracy numbers.

## UI Scope
- Trust Score current value and history.
- Prediction success/hit rates.
- Calibration and probability reliability.
- Performance by 1/2/3/5/7-day horizon.
- Performance by sector, market-cap bucket, regime, stock and setup when sample sizes permit.
- Benchmark-relative performance.
- Target/SL/expiry distribution.
- Evidence/sample-size indicators.
- Compact charts and grids with drill-down.

## API Contract
`GET /api/v1/performance/summary`
`GET /api/v1/performance/timeseries`
`GET /api/v1/performance/breakdown`
`GET /api/v1/trust`
`GET /api/v1/trust/history`

Query:
`horizon`, `sector`, `marketCap`, `regime`, `symbol`, `setup`, `from`, `to`.

Responses must include metric definitions, sample size, as-of timestamp, methodology version and benchmark where applicable.

## Acceptance Criteria
- Trust cannot be displayed without evidence/sample context.
- Small samples are visibly marked as statistically weak.
- User can see whether Trust is rising or falling over time.
- Metrics reconcile with closed prediction outcomes.
- Charts remain readable on mobile.
