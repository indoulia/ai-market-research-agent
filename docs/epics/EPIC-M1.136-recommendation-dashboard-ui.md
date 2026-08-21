# EPIC-M1.136 — Recommendation Dashboard UI

**Track:** UI
**Status:** VALIDATING
**Execution Status:** IMPLEMENTED_PENDING_MERGE
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

## Completion Report

**Implemented on branch:** `autonomous/epic-m1-136`, against the real, merged EPIC-M1.135 contract (`GET /api/v1/recommendations`, `docs/api/openapi.json`) — not a fixture, since M1.135 merged before this epic started.

**What was built:**
- `lib/core/api_client.dart` / `api_config.dart` / `api_exception.dart`: thin HTTP layer over `/api/v1`, decoding EPIC-M1.132's success/error envelope into a typed `ApiException` (`code`/`message`/`retryable`) rather than raw HTTP status.
- `lib/features/dashboard/recommendation.dart`: domain model parsed from `RecommendationSummary` JSON — decimal-as-string fields (`score`, `price`, `trustScore`, etc.) parsed once here, nullable fields kept nullable rather than defaulted.
- `lib/features/dashboard/recommendations_repository.dart`: the only place that talks to `/recommendations`; maps `horizon`/`sort`/`direction`/`pageSize`/`cursor` query params, returns items + `nextCursor` from `meta`. No client-side re-ranking (M1.135 AC).
- `lib/features/dashboard/dashboard_screen.dart`: the Home destination's real screen (replaces the M1.134 placeholder). KPI strip (opportunities count, avg trust, avg confidence — computed client-side over loaded items, see gap below), horizon selector (refetches on change), a 3-option sort filter bar (score/trust/upside), responsive 1/2/3-column card grid via `MraBreakpoints`, skeleton loading state, `MraStateView.error`/`.empty`, pull-to-refresh, cursor-based infinite scroll (loads more ~400px before the bottom, stops when `nextCursor` is null), tap-to-navigate to the existing M1.134 detail placeholder route with the real prediction `id`.
- **Real, additive fix to the already-merged EPIC-M1.133 `RecommendationCard`**: `currentPrice`/`changePercent`/`trust`/`companyName` are nullable in the real API response (a symbol can lack a current price, or trust score can be uncomputed). The component now renders "—" for a missing price (and omits the change row), omits the company subtitle when absent, and renders an explicit "N/A" trust badge instead of a fabricated low score — verified as zero-regression by running M1.133's existing test suite unmodified before adding new null-path tests (all passed unchanged).

**Tests:** `test/features/dashboard/dashboard_screen_test.dart` (loading skeleton, success + KPI strip, error + retry, empty state, N/A trust rendering, tap-to-navigate via a real `GoRouter`) plus 1 new test in `test/design_system/components_smoke_test.dart` for `RecommendationCard`'s null-handling. Full suite: `flutter test` → 40/40. `flutter analyze` → no issues. `dart format --set-exit-if-changed` → clean.

**Real bugs found and fixed during implementation:** the dashboard header's title `Text` wasn't wrapped in `Expanded`, overflowing at compact (368px bottom-nav) width — same overflow class already seen in M1.133/M1.134, now fixed here too. A test-fixture bug (not an app bug) where a `GoRoute` builder rendered `DashboardScreen` without a `Scaffold` ancestor, so `ChoiceChip` (inside `HorizonSelector`) couldn't find a `Material` widget — confirmed by reproducing, tracing to the missing `Scaffold`, and fixing the test rather than the component.

**Explicitly deferred / honest gaps, not fabricated:**
- KPI strip's "opportunities"/"avg trust"/"avg confidence" are computed over the *currently loaded* page(s), not a true global count — there's no dedicated stats endpoint yet. Labeled plainly as "Opportunities" rather than implying a platform-wide total.
- "Market regime" (present in M1.136's own Layout spec as a 4th KPI) has no backing API field anywhere in the current contract (`bootstrap` only carries `apiVersion`/`capabilities`/`serverTime`) — omitted rather than fabricated. Add it once a real market-regime field exists.
- `RecommendationCard`'s sparkline receives a flat 2-point series (`[price, price]`) since M1.135's response has no historical price series — an honest "no trend data" rendering, not invented history. A real sparkline needs either a new API field or a separate market-data endpoint.
- Sector/industry/marketCapBucket/minScore/minTrust filters from M1.135's contract are not yet exposed in the UI (only horizon + 3 sort options) — the repository layer already supports them; adding UI controls is incremental, not a contract gap.
