# EPIC-M3.3 — Opportunity Explorer

**Status:** DONE
**Execution Status:** COMPLETED
**Track:** UI + API
**Priority:** P0

## Objective
Allow users to efficiently discover and compare positive opportunities across the full analyzed universe without cluttering the home dashboard.

## UI Scope
- Search by symbol/name.
- Filter by market, horizon, sector, industry, market cap, liquidity and minimum Trust.
- Sort by Trust, score, upside, probability, freshness and ranking.
- Dense responsive data grid on web; compact cards/list on mobile.
- Pagination/infinite loading.
- Saved filter state within session.
- Clear indication of result count and data freshness.
- Drill into recommendation detail.

## API Contract
`GET /api/v1/opportunities`

Query parameters:
`market`, `horizon`, `sector`, `industry`, `marketCap`, `minTrust`, `minScore`, `minUpside`, `liquidityBucket`, `status`, `sort`, `page`, `pageSize`.

Response:
- `items[]`
- `page`
- `pageSize`
- `total`
- `asOf`
- `filters`

Items expose the same canonical recommendation summary contract as M3.2.

## Acceptance Criteria
- Filtering and sorting are server-side.
- Pagination is deterministic.
- Only positive-eligible opportunities are returned by default.
- API and UI handle empty results without visual clutter.
- Filter combinations do not require separate endpoint implementations.

## Completion Report (2026-08-22)

**Branching context:** `origin/autonomous/epic-m3-2` did not exist (not
yet pushed) when this branch (`autonomous/epic-m3-3`) was created, so per
the product owner's standing branching instruction it was based directly
on `origin/main` (`cfe84dd`). Re-checked immediately before opening the
PR: still not pushed, and `origin/main` had not moved. EPIC-M3.2 (Market
Overview & Home Dashboard) was therefore still `APPROVED`/not merged when
this PR was opened — this EPIC does not depend on M3.2's dashboard
screen or its `GET /api/v1/dashboard/snapshot` endpoint, only on the
canonical recommendation-summary *shape* M3.2's doc also references,
which already exists from EPIC-M1.135 (see below), so no blocking
dependency exists in practice.

**Context:** per `docs/epics/EPIC-M3-ROADMAP-NOTE.md`, this EPIC's
number was renumbered from a collision with the older split track; the
note's own renumbering table is imprecise about which split-track EPIC
"is" M3.3 (it maps `M3.3 -> was M1.134`, but old `M1.134` is "Flutter App
Shell & Responsive Navigation," an unrelated screen). Investigation
found the real, substantive overlap is with **`EPIC-M1.135 -
Recommendations Query API`** (`docs/epics/EPIC-M1.135-recommendations-api-and-query.md`,
`DONE`, merged PR #156) and its Flutter consumers (`M1.136` dashboard,
`M1.140` discover). This session's job was to diff M3.3's specific
scope against that existing, merged code -- not to build a second,
parallel screen or a second, parallel API for "the opportunity feed."

**Already satisfied by existing M1.135/M1.136/M1.140 work -- verified,
reused, not reimplemented:**
- The canonical recommendation-summary contract (`symbol`, `name`/`companyName`,
  `price`, `targetPrice`, `stopLoss`, `horizon`, `upsidePct`, `score`,
  `confidence`, `trustScore`, `status`, `updatedAt`, plus more) --
  `api/schemas/recommendations.py::RecommendationSummary`. Reused as-is
  for `/opportunities`' `items[]` per this epic's own instruction that
  items are "the same canonical recommendation summary contract as M3.2."
- The server-side join graph composing M1.87's ranking, M1.15's
  lifecycle, M1.77's trust score, M1.16's confidence classification and
  M1.47's publication -- `api/services/recommendations.py::list_recommendations`,
  reused as the structural template (not imported/shared as a function,
  matching this codebase's own existing precedent of `discovery.py` and
  `recommendations.py` each independently owning their full query rather
  than sharing a base-query abstraction).
- `market`, `horizon`, `sector`, `industry`, `minScore`, `minTrust`
  filters and `score`/`trust`/`upside` sort keys -- all pre-existing on
  `/recommendations`, carried over.
- `liquidity_bucket_expr`/`market_cap_bucket_expr` SQL expression
  builders (`api/services/segmentation.py`), already built for M1.139's
  `/discoveries` endpoint and reused here unchanged for `liquidityBucket`
  and `marketCap`.
- Page-based pagination primitives (`api/pagination.py::PageParams`,
  `MAX_PAGE_SIZE`) existed since EPIC-M1.132 but were **never actually
  used by any endpoint** (every existing list endpoint uses cursor
  pagination) -- confirmed by grep before use. `/opportunities` is the
  first real consumer, exactly the "future extension" `docs/api/VERSIONING.md`
  already anticipated.
- Flutter design-system pieces already built but **unused anywhere**:
  `MraDenseTable`/`MraColumn` (`flutter_app/lib/design_system/components/dense_data_table.dart`,
  built in EPIC-M1.133, zero call sites before this session) is exactly
  the "dense responsive data grid on web" UI Scope item -- adopted as-is
  rather than building a second grid component. `showMraBottomSheet`,
  `MraFilterBar`, `MraSearchField`, `RecommendationCard` reused the same
  way `dashboard`/`discover` already use them.
- Drill-into-detail: `RecommendationDetailScreen` + a nested
  `recommendation/:id` route is the proven pattern in all 4 existing
  branches; the new branch follows it exactly (`flutter_app/lib/app_shell/app_router.dart`).

**Genuine gaps found and implemented this session:**

*API* (`api/routers/opportunities.py`, `api/services/opportunities.py`,
`api/schemas/opportunities.py`, new):
- `GET /api/v1/opportunities` -- did not exist under any name; built new,
  page-based (`page`/`pageSize`/real `total` via `COUNT(*)`, affordable
  here since M1.135's own reason for avoiding one -- keyset pagination --
  doesn't apply to a page-based contract), returning
  `{ items, page, pageSize, total, asOf, filters }` exactly per this
  epic's documented Response shape (a new shape -- the existing generic
  `envelope.paginated()` helper's `data`/`meta.{page,pageSize,totalItems,totalPages}`
  shape doesn't match this epic's own field names, so `envelope.success()`
  wraps a purpose-built `OpportunityListResponse` instead).
- New filters: `minUpside` (reusing the existing upside-coalesce
  expression pattern), `liquidityBucket` (new to the recommendation
  feed -- previously only `/discoveries` had it), `status` (restricted
  to the two *open* lifecycle states, `ISSUED`/`AWAITING_HORIZON` --
  rejects `EVALUATED`/`UNEVALUABLE` with `MRA_VALIDATION_FAILED`, since
  this is a live opportunity explorer, not a historical archive; that's
  M3.4/M3.8's job), and server-side `search` (`ilike` over
  `Stock.symbol`/`Stock.company_name` -- no server-side search existed
  anywhere in `api/` before this).
- New sort keys: `probability` (`Prediction.predicted_probability`),
  `freshness` (a new SQL-computable proxy matching
  `context_summaries.evidence_freshness`'s own STALE/FRESH/UNKNOWN
  precedence via correlated `EXISTS` subqueries against
  `RecommendationEvidenceItem`, since that function itself only runs
  per-row in Python and isn't a sortable SQL expression), and `ranking`
  (documented as identical to `score` -- `app/opportunity_ranking.py`
  sorts its own output by `-composite_score`, so there is no separate
  "ranking" value to expose).
- Single-param `sort` with a `-` prefix for descending (e.g. `sort=-score`),
  matching the generic convention `docs/api/VERSIONING.md` already
  described as a "future, not yet needed" extension of M1.135's
  `sort`+`direction` pair -- now needed, so adopted and the doc updated
  to describe both conventions and when each applies.
- `marketCap` accepts the same bucket vocabulary as M1.135's
  `marketCapBucket` (`LARGE_CAP`/`MID_CAP`/`SMALL_CAP`/`UNCLASSIFIED`) --
  no other market-cap vocabulary (e.g. a numeric range) exists anywhere
  in this codebase to give the epic's shorter parameter name a different
  meaning; documented as a deliberate interpretation, not a literal
  numeric-range filter.
- `docs/api/openapi.json` regenerated (`python scripts/export_openapi.py`).
- `docs/api/VERSIONING.md` updated (Pagination and Sorting sections) to
  document `/opportunities` as the first page-based-pagination and
  first `-`-prefixed-sort consumer.

*UI* (`flutter_app/lib/features/opportunities/`, new feature folder):
- `opportunities_repository.dart` -- repository over `/opportunities`,
  reusing `dashboard/recommendation.dart`'s `Recommendation` model for
  items (same shape, avoids a second parallel DTO).
- `opportunity_explorer_screen.dart` -- new screen with: server-side
  debounced search; filters for market/horizon/market-cap/liquidity/min-trust
  (chip bars) plus free-text sector/industry fields, all grouped into a
  `showMraBottomSheet` "Filters" sheet (see below for why); a "Sort"
  bottom sheet with all 6 sort keys plus an ascending/descending toggle;
  a dense `MraDenseTable` grid at medium/expanded/large widths (>=600px)
  and a `RecommendationCard` list at compact (<600px) widths, per
  `MraBreakpoints`; page-based infinite scroll (fetches the next `page`
  when scrolled near the bottom, appending until `items.length >= total`);
  an explicit `"$total opportunities found"` + `"As of <relative time>"`
  freshness line; drill-in via `context.push('/opportunities/recommendation/$id')`.
  Filter/sort state lives on the `State` object, which -- like every
  other tab's screen -- survives switching tabs via `StatefulShellBranch`'s
  `IndexedStack`, satisfying "saved filter state within session" without
  new persistence machinery.
- New 7th app-shell destination ("Opportunities", `/opportunities`) in
  `flutter_app/lib/app_shell/app_destination.dart` and a new
  `StatefulShellBranch` in `app_router.dart` (with its own
  `recommendation/:id` sub-route, matching every other branch). Extended
  `app_shell_scaffold.dart`'s `Alt+1..6` keyboard-shortcut digit list to
  `Alt+1..7` to cover the new destination.
- **Mid-session design correction, found by the screen's own widget
  tests, not assumed:** an initial version put all 5 filter chip rows +
  2 text fields inline in the header. At a realistic phone viewport
  (e.g. 800x600 in the test harness), that header alone exceeded the
  available height, and the empty/error state's `SliverFillRemaining`
  was squeezed to zero height -- not just "below the fold" but actually
  unreachable by scrolling, since `hasScrollBody: false` sizes the sliver
  to `max(0, remaining)`. Fixed by moving all filters into a
  `showMraBottomSheet` (a pattern `filter_bar.dart`'s own docstring
  already anticipated: "Mobile screens may present the same options
  inside a bottom sheet") and sort into a second sheet, shrinking the
  permanent header to title + search + two buttons + a result-count
  line. This is a real UX fix, not just a test workaround.

**Tests (TDD):**
- `tests/test_api_opportunities.py` (18 new tests): empty feed;
  full-field shape + paging metadata; positive-only filtering;
  closed-lifecycle exclusion by default; `status` narrows to a specific
  open state; `status` rejects a terminal state (422); default
  score-descending order; `sort=trust` ascending; `sort=-ranking` matches
  `sort=-score`; `sort=-probability`; `minUpside` filter; `liquidityBucket`
  filter (HIGH vs. NORMAL -- LOW is impossible in this universe since
  M1.8's consensus gate requires `volume_ratio_20d >= 0.75`, documented
  in the test); `marketCap` bucket filter; `search` matches symbol or
  company name; page-based pagination covers every row exactly once
  across 3 pages and reports a correct `total`; stale evidence is
  reported not hidden; `sort=-freshness` ranks stale last; unknown sort
  rejected. Also added an autouse fixture clearing
  `api.rate_limit.default_limiter`'s shared, process-global state before
  and after this file's tests -- without it, this file's ~30 extra
  requests pushed the full suite's already-marginal shared rate-limit
  budget over 120 req/60s and caused unrelated `tests/test_api_tracking.py`
  tests (which run later, alphabetically) to fail with 429s; confirmed
  by running the full suite with and without this file.
- `flutter_app/test/features/opportunities/opportunity_explorer_screen_test.dart`
  (12 new tests): skeleton loading; result-count + freshness display;
  empty state; error state with retry (using `tester.ensureVisible`,
  since the result area sits below a scrollable header); dense table at
  wide widths vs. card list at compact widths; drill-in navigation;
  horizon/sort/min-trust filters (opened via their bottom sheets) each
  re-fetch with the right server params (verified via a
  call-recording fake repository, not just visual assertions); sort
  toggled twice flips direction; debounced search re-fetches with the
  term; explicit "N/A" trust cell (never a fabricated score).

**Validation run:**
```
python -m pytest tests/test_api_opportunities.py -q
# 18 passed in ~5s

python -m pytest -q
# 1348 passed, 9 skipped in 165.54s -- full existing suite + 18 new, no regressions

cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && flutter test
# All tests passed! (139 tests: 127 pre-existing + 12 new)
```

**Deliberately not done (rationale):**
- No `opportunities` capability flag added to `api/capabilities.py`'s
  `ApiCapabilities` -- the underlying domain capability is already
  covered by the existing `recommendations: true` flag (same domain,
  different query contract); adding a second flag for the same
  capability would be schema churn with no behavioral meaning.
- Sector/industry filters are free-text exact-match fields, not chip
  bars -- unlike market/horizon/marketCap/liquidity, there is no fixed,
  small enum for sector/industry anywhere in this codebase (no
  "known sectors" endpoint exists), so a chip bar isn't practical; a
  future EPIC that adds a sector/industry taxonomy endpoint could upgrade
  this without an API contract change.
- ETag/Last-Modified caching remains deferred, consistent with every
  other list endpoint's existing deferral (still no endpoint in this
  codebase implements it).
- No ascending/descending toggle was added to the Explorer's per-metric
  sort *chips* beyond the Sort sheet's single global direction switch
  (matching `dashboard_screen.dart`'s existing simpler pattern of one
  implicit default direction per screen); a per-field-remembered
  direction was judged unnecessary complexity for this session's scope.

**Conclusion:** the bulk of the underlying data/domain composition
(M1.87/M1.15/M1.77/M1.16/M1.47 via M1.135's join-graph pattern),
segmentation helpers (M1.139), page-based pagination primitives
(M1.132, previously unused), and several Flutter design-system
components (`MraDenseTable`, `showMraBottomSheet`, M1.133) already
existed and were reused rather than reimplemented. The genuine new work
was: the `/opportunities` endpoint itself (page-based contract, 4 new
filters, 3 new sort keys, server-side search); a brand-new Opportunity
Explorer screen and its 7th app-shell destination; and a real UX fix
(bottom-sheet filters) discovered by the screen's own tests. Marking
this EPIC `DONE`.
