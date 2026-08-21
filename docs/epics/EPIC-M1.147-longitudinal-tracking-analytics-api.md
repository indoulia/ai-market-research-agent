# EPIC-M1.147 — Longitudinal Tracking & Performance Analytics API

**Track:** API
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Expose historical recommendation and model performance in a compact analytical contract so users can see whether MRA is improving over time.

## Contracts
`GET /api/v1/tracking/summary?range=7d|30d|90d|1y`

Response: `predictionCount,closedCount,targetHitRate,stopLossRate,horizonExpiryRate,avgRealizedReturn,avgPredictedReturn,calibrationScore,trustScore,trustDelta,modelVersion,benchmarkReturn,relativeReturn`.

`GET /api/v1/tracking/timeseries?metric=trust|hitRate|return|calibration&range=&bucket=day|week`

`GET /api/v1/tracking/breakdown?dimension=horizon|sector|marketCap|regime|setup`

`GET /api/v1/tracking/predictions?status=active|closed&cursor=`

## Rules
- Metrics are calculated from immutable outcome history.
- Closed prediction counts and denominators are explicit.
- Small samples are flagged rather than presented as authoritative.
- Benchmark-relative results are separate from raw returns.
- Trust is displayed with evidence/sample context.

## Acceptance Criteria
- API can render a historical Trust Score series.
- API can show outcome performance over selectable periods.
- API supports horizon/sector/regime breakdowns.
- Metrics are reproducible and versioned.
- No metric silently mixes prediction versions or incomplete outcomes.

## Parallelization
API analytics team.

## Dependencies
M1.88, M1.89, M1.119, M1.122, M1.129.
