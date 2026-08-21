# EPIC-M1.138 — Recommendation Detail & Longitudinal History UI

**Track:** UI
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Give the user a compact but deep view of one recommendation: why it exists, current target/SL state, confidence/trust, evidence and how the prediction evolved over time.

## Layout
Desktop:
- Header identity + current price.
- Compact target/SL/horizon/score/confidence/trust grid.
- Main chart area for price vs target/SL and prediction revisions.
- Side panel for fundamentals/news/events/evidence.
- Bottom timeline for revisions and outcome.

Mobile:
- Header + key metric grid.
- Price/target/SL chart.
- Evidence sections as collapsible panels.
- Revision timeline below.

## Required Views
- Current prediction
- Prediction revisions
- Daily tracking
- Target/SL status
- Outcome
- News/events that changed the prediction
- Evidence/provider summary
- Benchmark-relative result
- Trust/confidence history

## UX Rules
- Most important information appears above the fold.
- Use grids and compact sections rather than long prose.
- Charts must have readable axes/tooltips and never be the sole source of numeric truth.
- Explain Trust, Confidence and Score separately.
- Show stale/fresh indicators visibly but unobtrusively.

## Acceptance Criteria
- User can understand current recommendation in under one screen on desktop.
- User can inspect historical revisions without leaving the detail screen.
- Target/SL hits are visually obvious.
- Historical data is never shown as current data.
- Responsive behavior works without horizontal scrolling except intentionally scrollable charts/tables.

## Parallelization
UI implementation against M1.137 fixture/OpenAPI data.

## Dependencies
M1.133, M1.134, M1.137.
