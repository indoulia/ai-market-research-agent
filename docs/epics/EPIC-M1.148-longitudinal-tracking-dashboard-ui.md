# EPIC-M1.148 — Longitudinal Tracking Dashboard UI

**Track:** UI
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Give users a clean historical view of MRA performance, prediction outcomes and Trust Score evolution without turning the app into an analytics-heavy cluttered dashboard.

## Layout
- Compact top KPI grid: active, closed, target-hit, average return, Trust.
- Main Trust Score trend chart.
- Secondary outcome trend chart.
- Horizon/sector/regime breakdown as compact selectable cards.
- Recent closed recommendations table/list.

## UX Rules
- Default range: 30 days; quick options 7d/30d/90d/1y.
- Show sample size alongside rates.
- Clearly distinguish predicted vs realized return.
- Use tooltips for statistical terms.
- Avoid more than 2–3 primary charts per view.
- Allow drill-down to the recommendation detail/history screen.

## Acceptance Criteria
- User can see whether Trust is improving over time.
- User can compare outcomes across horizons.
- Small-sample warnings are visible.
- Charts are responsive and readable on mobile.
- No dashboard widget duplicates calculations already returned by the API.

## Parallelization
UI analytics team against M1.147 fixtures/OpenAPI.

## Dependencies
M1.133, M1.134, M1.147.
