# EPIC-M1.136 — Recommendation Dashboard UI

**Track:** UI
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Create the primary MRA screen: a clean, high-signal recommendation dashboard that lets a user understand today's best short-term opportunities in seconds without visual clutter.

## Layout
Desktop/web:
- Header: market status, last refresh, compact global filters.
- KPI strip: opportunities, average Trust, average confidence, market regime.
- Main grid: recommendation cards/table hybrid.
- Optional right-side compact market context panel.

Mobile:
- KPI strip becomes horizontal scroll.
- Recommendation cards become vertically stacked dense cards.
- Filters become bottom sheet.

## Recommendation Card
Must show at a glance:
- Symbol/company
- Current price/change
- Horizon
- Target
- Stop loss
- Upside %
- Score
- Confidence
- Trust
- Compact fundamental/news/event indicators
- Last updated/freshness

Use visual hierarchy, not oversized typography. Icons should reinforce meaning; tooltips/explanations should be available for unfamiliar metrics.

## Interaction
- Tap/click opens recommendation detail.
- Sort/filter without losing scroll position.
- Pull/command refresh.
- Loading skeletons instead of layout jumps.
- Clear empty state.
- Clear stale/offline state.
- No auto-refresh that unexpectedly moves the user's scroll position.

## Acceptance Criteria
- Primary recommendation is visible without excessive scrolling.
- No screen has unnecessary decorative whitespace.
- Cards remain readable at narrow widths.
- Web supports hover/tooltips and keyboard navigation.
- Mobile supports touch targets and swipe-safe interactions.
- UI uses only M1.135 response data; no duplicated recommendation logic.

## Parallelization
UI implementation against M1.135 fixture/OpenAPI data.

## Dependencies
M1.133, M1.134, M1.135.
