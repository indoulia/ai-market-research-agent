# EPIC-153 — Market Overview & Home Dashboard

**Status:** DONE
**Execution Status:** COMPLETED
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

## Completion Report (2026-08-22)

**Context:** see `docs/epics/EPIC-M3-ROADMAP-NOTE.md`. The older split
track's EPIC-138 (Recommendations Query API) + EPIC-139 (Recommendation
Dashboard UI) already ship most of the *same product surface* this EPIC
asks for — a Home screen showing top positive opportunities with
price/target/SL/upside/horizon/score/trust, sort/horizon filters, skeleton
loading, empty/error states. Diffing EPIC-153's own explicit API contract and
UI Scope line-by-line against that merged code (not against the general
product idea) found this EPIC is **not** ~95% satisfied like EPIC-152 was —
the specific `GET /api/v1/dashboard/snapshot` single-request contract and
several named widgets (events strip, recent-changes, trust summary,
market-status header, sector/market/size quick filters) were genuine,
concrete gaps. Implemented as an extension of the existing API/app, not a
second parallel dashboard.

**Already satisfied by existing EPIC-138/EPIC-139 (+EPIC-142/EPIC-150) work —
verified, not reimplemented:**
- Top positive opportunities with price/target/SL/upside/horizon/score/
  confidence/trust in a responsive card grid, dense desktop / stacked
  mobile — `flutter_app/lib/features/dashboard/dashboard_screen.dart`
  (`MraBreakpoints`-driven 1/2/3-column grid, unchanged from EPIC-139),
  `design_system/components/recommendation_card.dart`.
- Skeleton loading, empty state, error+retry state, N/A trust indicator
  (never a fabricated score) — `design_system/components/skeleton_loader.dart`,
  `state_views.dart`, unchanged.
- Navigation into the full recommendation detail view on card tap —
  unchanged `context.push('/home/recommendation/${id}')` route (EPIC-141's
  `RecommendationDetailScreen`).
- Positive-only, immutable-prediction product constraints — inherited
  unchanged from EPIC-138's `RECOMMENDATION_LABEL = "POSITIVE_OPPORTUNITY"`
  and EPIC-018's open-lifecycle-only feed; nothing in this EPIC touches
  recommendation generation, only read-side composition/display.
- Underlying market-regime/index/news/event/trust-history data sources —
  EPIC-142's `market.py`/`news_events.py` services and EPIC-150's
  `tracking.py` (`get_summary`), reused verbatim, not recomputed.

**Genuine gaps found and implemented this session:**
- `GET /api/v1/dashboard/snapshot` (query: `market`, `horizon`, `limit`,
  plus additive `sector`/`marketCapBucket` — see note below) — new
  `api/routers/dashboard.py`, `api/schemas/dashboard.py`,
  `api/services/dashboard.py`. A pure read-side *composition* over
  already-merged, already-tested query services: `list_recommendations`
  (EPIC-138, `sort=score` for `topOpportunities`, `sort=updatedAt` for
  `recentChanges`), `get_market_summary` (EPIC-142) for
  `marketStatus`/`marketRegime`/`indices`/`asOf`, `list_news`/`list_events`
  (EPIC-142) merged server-side into one time-ordered `importantEvents`
  feed, and `get_summary` (EPIC-150, fixed 30d window) for `trustSummary`.
  No new ranking/business logic — only field renaming, merging, and
  capping to `limit`.
- `DashboardOpportunity` adds one field beyond the EPIC's own "must expose
  at minimum" list: `id`. Without it, "navigation into full
  opportunity/detail views" (an explicit AC) is impossible against the
  existing `/recommendation/:id` route. The EPIC's "at minimum" framing
  permits this — it is not a second, divergent recommendation shape, the
  same underlying row `/recommendations` returns.
- "Recently changed recommendations": no lifecycle-transition-history
  table exists anywhere in this platform (checked `app/lifecycle.py` and
  `app/models.py`) — an honest design choice, not a gap to fabricate
  around: `recentChanges` is the same open, positive-only feed ordered by
  recency of lifecycle update (`sort=updatedAt`) rather than score.
  Documented in `api/services/dashboard.py`'s own module docstring.
- `sector`/`marketCapBucket` query params on the snapshot endpoint: the
  EPIC's own API Contract section lists only `market`/`horizon`/`limit`,
  but its UI Scope separately requires "quick filters for horizon, market,
  sector and size" — unsatisfiable together without extending the query
  surface. Added both as additive, optional params reusing EPIC-138's exact
  existing `sector`/`marketCapBucket` vocabulary (not a new filter
  contract) so the UI's quick filters actually take effect on the
  snapshot's initial load, not just on a second, separate request.
- `ApiCapabilities.dashboard` flipped to `true` (`api/capabilities.py`,
  `api/schemas/bootstrap.py`), plus `docs/api/openapi.json` regenerated.
- Flutter: `flutter_app/lib/features/dashboard/dashboard_snapshot.dart`
  (domain models), `dashboard_repository.dart` (the snapshot repository
  boundary), and `dashboard_screen.dart` rewritten so the Home
  destination's **initial paint is exactly one request** to
  `/dashboard/snapshot` (AC) — market-status/regime header, a trust-summary
  widget, an important-events horizontal strip (rendered only when
  non-empty, so it never dominates the screen — AC), a recently-changed
  list, and the top-opportunities grid all come from that one response.
  Quick filters (horizon — reusing EPIC-139's existing `HorizonSelector`;
  market and size-bucket — reusing EPIC-143's `MraFilterBar` chip pattern;
  sector — a plain text field, since sector has no fixed enum) all refetch
  the snapshot on change. `RecommendationsRepository.fetchPage` extended
  with `market`/`sector`/`marketCapBucket` (previously only `horizonDays`)
  so scrolling past the snapshot's own top-N stays consistent with the
  same active filters.
- Scrolling past the snapshot's bounded `topOpportunities`: the snapshot
  contract carries no cursor of its own (by design — it is a compact
  overview, not a paginated list), so a manual "Load more opportunities"
  footer button performs one "bootstrap" call to the identically-sorted/
  filtered `/recommendations` page 1 to recover a real EPIC-138 keyset
  cursor, dedupes by `id` against what the snapshot already showed, and
  falls straight through to the genuine next page if that leaves nothing
  new — so the first tap is never a visible no-op.

**Tests (TDD):**
- Backend — `tests/test_api_dashboard.py` (13 new tests): honest empty-
  state defaults, full opportunity field mapping incl. the added `id`,
  company-name-null → symbol fallback, positive/open-lifecycle-only
  filtering, score-descending default order, `recentChanges` ordered by
  `updatedAt` (not score, proven with a low-score-but-recently-updated
  row), `market`/`horizon`/`sector`/`marketCapBucket` filters applied to
  both `topOpportunities` and `recentChanges`, `limit` bounding both
  lists, market-summary field passthrough, news+corporate-action merge
  ordering, and `trustSummary` reflecting a real `tracking.get_summary`
  window. Plus 2 updated capability assertions in
  `tests/test_api_contract.py`.
- Flutter — `flutter_app/test/features/dashboard/dashboard_screen_test.dart`
  rewritten against the new snapshot-driven architecture: skeleton
  loading, opportunities + market-status + trust-summary rendering,
  events-strip presence/absence, recently-changed widget, small-sample
  badge, error+retry, empty state, N/A trust, tap-to-navigate using the
  snapshot's `id`, the bootstrap-then-cursor "Load more" flow (dedup
  proven with a deliberately-duplicate bootstrap page), 2x-text-scale
  overflow regression, and a 50-item render check. Also updated
  `flutter_app/test/e2e/end_to_end_journey_test.dart` (the Home
  destination's real load now scripts `/api/v1/dashboard/snapshot`, not
  `/recommendations`, across the happy path and all four dashboard-load
  failure paths) and the `RecommendationsRepository.fetchPage` override
  signatures in `discover_screen_test.dart`/`news_events_screen_test.dart`.

**Real bugs found and fixed during implementation (not this EPIC's own
code, but blocking its own tests going green):**
- `api/services/keyset.py`-style tzinfo round-trip: SQLite drops tzinfo on
  `DateTime(timezone=True)` columns, so merging `NewsEventRecord.published_at`
  and a Python-constructed aware `CorporateAction` effective-date datetime
  and sorting them together raised `TypeError: can't compare offset-naive
  and offset-aware datetimes` — fixed by normalizing both sides in
  `api/services/dashboard.py::_as_aware_utc` before any comparison/`max()`,
  the same class of fix already applied in `api/services/tracking.py`.
- A genuinely pre-existing, unrelated (EPIC-150) test-infra fragility:
  `api/rate_limit.py`'s `default_limiter` is a process-wide singleton
  keyed by client host, shared by every API test file in one `pytest`
  process. Adding `tests/test_api_dashboard.py`'s ~40 extra HTTP requests
  pushed the *existing* full-suite request volume over the fixed-window
  limit within the same 60s window, intermittently 429-ing an unrelated
  EPIC-150 tracking test later in the run (reproduced deterministically via
  bisection: passed with the file excluded, failed with it included,
  regardless of insertion order). Fixed narrowly, in-scope: an autouse
  fixture in `tests/test_api_dashboard.py` alone resets
  `default_limiter._hits` before/after each of its own tests, so this
  file's request volume never leaks into another file's budget — no
  change to `api/rate_limit.py` or any other EPIC's test file.

**Validation run:**
```
python -m pytest -q
# 1342 passed, 9 skipped in ~190s -- full existing suite, no regressions,
# run twice to confirm the rate-limiter fix removed the flake.

cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && dart format --set-exit-if-changed lib test
# Formatted 110 files (0 changed) -- clean.

cd flutter_app && flutter test
# All tests passed! (130 tests)
```

**Deliberately not done (rationale):**
- `indices[]` stays always `[]` and `marketStatus` stays always
  `"UNKNOWN"` — both inherited, honestly, from EPIC-142's own named gaps (no
  index-level price feed or market-calendar module exists anywhere in
  this platform). Fabricating either would violate this repo's "never
  fabricate" rule; the UI renders "Market status unavailable" rather than
  hiding or guessing it.
- No new "important events materiality ranking" logic: `importantEvents`
  merges EPIC-142's `/news`/`/events` by recency only (same as the existing
  EPIC-143 UI's client-side merge), since no cross-source materiality
  scoring module exists to rank by importance rather than time.
- No automatic infinite-scroll on the Home dashboard (unlike the old
  EPIC-139 screen it replaces): a compact "first screen" overview with a
  bounded, capped snapshot is the product intent here; a manual "Load
  more" affordance still gives full access to the underlying feed without
  making the dashboard behave like an unbounded list by default.
- Sector filter is a free-text field, not a chip bar: `sector` has no
  fixed, small enum anywhere in the schema (unlike `marketCapBucket`), so
  a chip bar would need to either hardcode a sector list (fabricated) or
  fetch one from a non-existent endpoint.
