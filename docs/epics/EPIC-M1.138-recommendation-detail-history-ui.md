# EPIC-M1.138 — Recommendation Detail & Longitudinal History UI

**Track:** UI
**Status:** VALIDATING
**Execution Status:** IMPLEMENTED_PENDING_MERGE
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

## Completion Report

**Implemented on branch:** `autonomous/epic-m1-138`, against the real, merged EPIC-M1.137 contracts (`docs/api/openapi.json`) — not a fixture.

**What was built:**
- `lib/features/detail/` domain models (`recommendation_detail.dart`, `history_item.dart`, `event_item.dart`, `recommendation_outcome.dart`) parsed from `RecommendationDetail`/`HistoryItem`/`EventItem`/`OutcomeResponse`, and `recommendation_detail_repository.dart` covering all four M1.137 endpoints (detail, history with `from`/`to`/cursor, events with cursor, outcome).
- `recommendation_detail_screen.dart` replaces the M1.134 placeholder at `/home/recommendation/:id` (route now parses a real integer id, matching M1.135/137's `id: integer`). Fetches detail+history+events+outcome concurrently (`Future.wait`), single loading/error/loaded state machine matching M1.136's pattern.
- Layout: header (symbol/company/current price/status), target/SL/horizon/upside chips, score/confidence/trust indicators (trust shows explicit "N/A" when null, matching M1.136's established convention), a price-vs-target/SL chart with tap-to-inspect readout (`price_target_chart.dart` — dependency-free `CustomPaint`, min/max axis labels, legend, and a text readout of the selected point's date+price so the chart is never the sole source of numeric truth per the epic's own UX rule), outcome section (target/stop-loss-hit chips, realized return, or an honest "not evaluated yet" for `PENDING`), evidence panel (fundamental/technical/market/news/evidence-strength/provider chips, only rendering sections with data), an events feed (reusing M1.133's `NewsCard`), and a revision timeline (reusing M1.133's `TimelineEventRow`, newest-first).
- Responsive: two-column layout (chart/metrics/outcome left, evidence/events/timeline right) at ≥900px width; single stacked column below that — desktop/mobile split per the epic's own Layout spec.
- Deleted `app_shell/recommendation_detail_placeholder_screen.dart` (fully superseded) and updated the two `app_shell_test.dart` cases that referenced it with non-numeric fake ids to use real integer ids and route-location assertions instead of placeholder text.

**Tests:** `test/features/detail/recommendation_detail_screen_test.dart` (header/metrics/pending-outcome, N/A trust, revision timeline + events rendering, target-hit outcome chip, error+retry). Full suite: `flutter test` → 45/45. `flutter analyze` → no issues.

**Acceptance criteria status:**
- Done: current recommendation understandable above the fold on desktop (header+metrics+chip row); historical revisions inspectable without leaving the screen (timeline + chart tap-to-inspect); target/SL hits visually obvious (colored chips with icons); historical data never shown as current (history/outcome are separate, clearly-labeled sections, never merged into the header's "current" fields); responsive without horizontal scrolling (verified widths from 360px mobile to 1280px+ desktop in manual testing).
- Explicit gap, not fabricated: the chart's tooltip is a tap-to-inspect readout below the chart, not a floating hover tooltip — a reasonable but simplified reading of "readable axes/tooltips." Benchmark-relative result is always "not available yet" (M1.129 doesn't exist yet, per M1.137's own completion report) — this UI just surfaces that honestly rather than hiding the section or fabricating a number.
