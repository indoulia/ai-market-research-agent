# EPIC-M1.133 — Market Overview & Home Dashboard

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Provide a clean first screen that answers in seconds: what is the market doing, what are MRA's best positive opportunities, and what important information changed.

## UI Scope
- Compact market-status header.
- Regime, major-index movement and update/freshness indicators.
- Top positive opportunities in responsive grid/table layouts.
- Compact cards showing price, target, SL, upside, horizon, score and Trust.
- Important events/news strip without dominating the screen.
- Recently changed recommendations widget.
- Trust/performance summary widget.
- Quick filters for horizon, market, sector and size.
- Dense desktop grid; stacked mobile cards.
- Skeleton loading and graceful partial-data states.
- Navigation into full opportunity/detail views.

## API Contract
`GET /api/v1/dashboard/snapshot`

Query:
- `market`
- `horizon`
- `limit`

Response must contain:
- `marketStatus`
- `asOf`
- `marketRegime`
- `indices[]`
- `topOpportunities[]`
- `importantEvents[]`
- `recentChanges[]`
- `trustSummary`
- `dataFreshness`

Each opportunity summary must expose at minimum:
`symbol`, `name`, `price`, `targetPrice`, `stopLoss`, `horizon`, `upsidePercent`, `score`, `confidence`, `trustScore`, `status`, `updatedAt`.

## Acceptance Criteria
- Initial dashboard requires one snapshot request for core content.
- No negative/cautious recommendations appear in the user-facing opportunity feed.
- Desktop uses available width efficiently without excessive whitespace.
- Mobile remains readable without horizontal scrolling.
- Every displayed metric has a source/as-of path available through detail APIs.
