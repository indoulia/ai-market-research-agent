# EPIC-M1.139 — Active Prediction Monitoring

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Give users a compact live view of active positive recommendations and their current distance to target, stop-loss and horizon expiry.

## UI Scope
- Active recommendation grid/list.
- Current price, target, SL, distance-to-target, distance-to-SL.
- Horizon remaining.
- Trust and freshness.
- Last event/revision indicator.
- Target-hit and SL-hit transition states.
- Compact progress visualization.
- User-selectable refresh behavior with server freshness.

## API Contract
`GET /api/v1/predictions/active`
`GET /api/v1/predictions/active/{predictionId}`

Response:
`predictionId`, `symbol`, `price`, `targetPrice`, `stopLoss`, `horizon`, `remainingTradingDays`, `distanceToTargetPercent`, `distanceToStopLossPercent`, `score`, `confidence`, `trustScore`, `status`, `lastPriceAt`, `lastRevisionAt`, `nextEvaluationAt`.

## Acceptance Criteria
- Active state is sourced from M1.119, not recomputed differently in Flutter.
- Target/SL closure appears consistently after outcome confirmation.
- Stale data is clearly indicated.
- No user-facing negative recommendation states are introduced.
