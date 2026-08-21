# EPIC-M1.137 — Recommendation Detail, Revision & History API

**Track:** API
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Expose a complete, versioned recommendation detail and longitudinal history model so the Flutter app can explain not only the current prediction but how it changed and what happened afterward.

## Contracts
`GET /api/v1/recommendations/{id}` — current recommendation.

`GET /api/v1/recommendations/{id}/history?from=&to=&cursor=` — prediction revisions and daily tracking snapshots.

`GET /api/v1/recommendations/{id}/events?cursor=` — material news/events/reanalysis triggers.

`GET /api/v1/recommendations/{id}/outcome` — target/SL/horizon outcome and evidence.

## Detail Response
`id, symbol, exchange, companyName, predictionVersion, createdAt, updatedAt, asOf, entryPrice, currentPrice, targetPrice, stopLoss, horizonDays, expiryAt, upsidePct, probability, score, confidence, trustScore, uncertainty, evidenceStrength, fundamental, technical, market, news, events, benchmarkRelative, liquidity, providerEvidence, status`

## History Item
`timestamp, version, price, targetPrice, stopLoss, probability, score, confidence, trustScore, triggerType, triggerEventId, changeSummary`

## Outcome
`status, detectedAt, observedPrice, realizedReturnPct, targetHit, stopLossHit, horizonExpired, benchmarkReturnPct, evidenceId`

## Acceptance Criteria
- Historical versions are immutable.
- Current detail is never reconstructed by mutating history.
- History can explain every material revision.
- Outcome data includes exact detection evidence.
- Pagination and date filtering are stable.
- API does not expose internal negative/cautious recommendation categories as user-facing recommendations.

## Parallelization
API implementation. UI M1.138 must consume these contracts exactly.

## Dependencies
M1.132, M1.105, M1.119, M1.126, M1.129.
