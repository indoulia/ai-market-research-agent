# EPIC-M3.13 — Responsive, Accessibility & Performance

**Status:** DONE
**Execution Status:** COMPLETED
**Track:** UI + API
**Priority:** P0

## Objective
Make the MRA application fast, accessible, responsive and visually consistent across mobile and web without sacrificing information density.

## UI Scope
- Responsive layouts based on available width.
- Keyboard, mouse, touch and screen-reader support.
- Semantic labels for icons and charts.
- Proper text scaling and contrast.
- Virtualized/lazy lists and grids where required.
- Skeleton loading and progressive rendering.
- Preserve scroll/filter/navigation state.
- Avoid unnecessary animation; use purposeful transitions only.
- Performance budgets for first render, navigation and large result sets.
- Iconography must use a consistent professional icon set; icons never replace necessary text without accessible labels.

## API Scope
- Pagination and bounded payloads.
- Field selection/summary endpoints where useful.
- Cache headers/ETags where safe.
- Efficient dashboard aggregation.
- Compression and response-size monitoring.
- Server timing/correlation metadata.

## Acceptance Criteria
- No horizontal scrolling on supported mobile layouts.
- Large desktop screens use grids/columns efficiently.
- Accessibility checks pass defined project gates.
- Core screens meet agreed performance budgets on representative mobile/web hardware.
- APIs avoid returning unnecessary historical/detail payloads for summary views.

## Completion Report

**Context:** this EPIC is cross-cutting (an audit, not a new screen), per its
own framing and `docs/epics/EPIC-M3-ROADMAP-NOTE.md`. EPIC-M1.143
(`docs/epics/EPIC-M1.143-responsive-accessibility-performance-quality.md`,
`DONE`) already did this same audit-and-fix pass over the six screens that
existed at the time (dashboard, discover, market, preferences, detail,
news/events) and over shared design-system components (`MraChip`,
`ScoreIndicator`, `TargetSlBadge`, `KpiStatCard`) that every later screen
also reuses. This session's job was to audit everything M1.143 could not
have covered because it did not exist yet: the newer M3.2-M3.12 screens
(opportunity explorer, recommendation detail, tracking/active-position
monitoring, learning, feedback history, system health, sign-in/splash) and
this EPIC's own explicit API Scope, which M1.143 (a UI-only epic) never
touched at all.

**Audited (read in full, cross-checked against the UI Scope bullets):**
`opportunity_explorer_screen.dart`, `recommendation_detail_screen.dart`
(+ `price_target_chart.dart`), `tracking_screen.dart` (+
`active_prediction_card.dart`, `tracking_trend_card.dart`),
`learning_screen.dart`, `feedback_history_screen.dart`,
`system_health_screen.dart`, `sign_in_screen.dart`, `splash_screen.dart`,
`general_settings_screen.dart`, `quick_preferences_screen.dart`,
`chip_list_editor.dart`, `dense_data_table.dart`, `sparkline_chart.dart`,
plus a project-wide grep sweep for `IconButton(` (icon-only controls
missing an accessible name), `AnimationController`/`Animated*` (unpurposeful
animation), and the API's `api/app.py`/`api/middleware.py` cross-cutting
layer.

**Already compliant, verified not re-implemented:** every audited screen
already used `LayoutBuilder`/`MraBreakpoints` for width-based responsive
layout (not device-type branching), cursor-based "Load more" pagination
bounding every list to a loaded window, `SkeletonCard` loading states,
`MraStateView.error/.empty` with retry, chip-based filter/sort state kept
alive across tab switches via the shell's `IndexedStack`, `Semantics`
containers on filter/selector rows, and a consistent Material icon set
throughout. `PriceTargetChart`/`SparklineChart` already carry `Semantics`
labels; axis min/max and the exact numeric values are always shown as text
next to the chart, never only in the drawing. No unpurposeful animation
exists anywhere in the app (`skeleton_loader.dart`'s shimmer is the only
`Animated*` usage in `lib/`, and it is the loading-state signal itself).
Dashboard aggregation is already a single `GET /api/v1/dashboard/snapshot`
call, not N+1 fetches. Correlation metadata (`X-Request-Id`) already
existed from EPIC-M1.132.

**Genuine gaps found and fixed (UI):**
- `flutter_app/lib/features/auth/splash_screen.dart` — the session-restore
  spinner had no `Semantics` label at all; a screen reader announced
  nothing during startup. Wrapped in `Semantics(label: 'Restoring your
  session', ...)`.
- `flutter_app/lib/features/auth/sign_in_screen.dart` — the submit
  button's `Text('Continue')` child was replaced by a bare spinner while
  submitting, with no accessible name in that state (this EPIC's own AC:
  "icons never replace necessary text without accessible labels" — the
  same failure mode, just via a spinner instead of an icon). Wrapped in
  `Semantics(button: true, label: 'Continue'/'Continue, submitting') +
  ExcludeSemantics` so the button keeps a real accessible name throughout.
- `flutter_app/lib/features/preferences/chip_list_editor.dart` — the
  "add" `IconButton` had no `tooltip` (nameless icon-only control); added
  `tooltip: 'Add ${label}'`. Also gave each removable `Chip` a specific
  `deleteButtonTooltipMessage: 'Remove $v'` instead of the generic default.
- `flutter_app/lib/features/preferences/quick_preferences_screen.dart` —
  `_SaveStatusLabel` ("Saving…"/"Saved"/"Save failed") is the *only* signal
  that an autosave (triggered by every toggle/chip on the form) succeeded
  or failed; wrapped it in `Semantics(liveRegion: true, ...)` so a screen
  reader announces the change instead of relying on a sighted user noticing
  the text swap.

**Genuine gaps found and fixed (API Scope — this EPIC's own scope was
entirely unaddressed before this session; EPIC-M1.132/M3.1 only shipped
the envelope/pagination/correlation-id foundation, not these):**
- **Compression:** no compression middleware existed anywhere. Added
  `GZipMiddleware(minimum_size=500)` in `api/app.py`, added last so it is
  outermost in Starlette's middleware stack (compresses the fully-formed
  response, headers included, from every layer below it).
- **Server timing/correlation metadata:** correlation (`X-Request-Id`)
  already existed; timing did not. `api/middleware.py`'s
  `RequestContextMiddleware` now also sets a standard, client-parseable
  `Server-Timing: total;dur=<ms>` header on every `/api/v1` response.
- **Response-size monitoring:** there was no visibility into oversized
  payloads at all. The same middleware now logs a `WARNING` (`api.middleware`
  logger) whenever a response's `Content-Length` exceeds
  `LARGE_RESPONSE_BYTES` (250 KB) — a real, testable hook for ops
  monitoring rather than a fabricated "monitoring exists" claim.
- **Cache headers/ETags:** EPIC-M3.1's own completion report explicitly
  deferred this, naming the missing precondition as "no endpoint with
  cacheable, slowly-changing data that needs it." `GET /api/v1/version` and
  `GET /api/v1/capabilities` (`api/routers/meta.py`) are exactly that — both
  are build-time constants, never DB-derived. Added a deterministic
  content-hash `ETag`, `Cache-Control: public, max-age=300`, and a real
  `304 Not Modified` short-circuit on a matching `If-None-Match`.
- **Pagination and bounded payloads:** `GET /api/v1/learning/experiments`
  (EPIC-M3.9) had no limit at all, unlike its sibling `/learning/history`
  (which already bounds to `DEFAULT_HISTORY_LIMIT=50`/`MAX=200`). Added the
  identical bounded `limit` query param (`DEFAULT_EXPERIMENTS_LIMIT=50`,
  `MAX_EXPERIMENTS_LIMIT=200`) to `api/services/learning.py`'s
  `list_learning_experiments` and `api/routers/learning.py`'s endpoint, so
  experiments accumulating over the platform's lifetime can no longer
  return an unbounded array.

**Not a gap, verified:** `MraDenseTable`/dashboard/discover/tracking card
lists render via `Column`, not `ListView.builder` — not virtualized in the
strict sense, but every one of them is already paired with cursor-based
"Load more" pagination bounding what's in memory to one loaded page (the
same pattern M1.143 left unflagged on the six screens it audited); this
session found no screen that renders an unbounded, un-paginated list.

**Tests (TDD — each fix has a regression test that fails against the
pre-fix code):**
- Flutter: `flutter_app/test/features/auth/splash_screen_test.dart` (new),
  `sign_in_screen_test.dart` (submit-button semantics-label-preserved
  test, using a never-resolving `Completer`-backed fake repository),
  `preferences/chip_list_editor_test.dart` (new — tooltip assertions),
  `preferences/quick_preferences_screen_test.dart` (live-region flag
  assertion via `tester.ensureSemantics()`/`getSemantics`).
- Python: `tests/test_api_contract.py` — `test_version_and_capabilities_are_cacheable_with_etag`
  (ETag/Cache-Control + real 304 round-trip), `test_every_api_response_carries_server_timing_header`,
  `test_large_api_responses_are_gzip_compressed` (probe app via the real
  `register_api()`, asserts `Content-Encoding: gzip`),
  `test_oversized_response_is_logged_for_monitoring` (monkeypatches the
  threshold low, asserts the WARNING log via `caplog`).
  `tests/test_api_learning.py` —
  `test_experiments_endpoint_respects_limit_and_returns_newest_first`.

**Validation run:**
```
python -m pytest tests/test_api_contract.py tests/test_api_learning.py -q
# 28 passed

python -m pytest -q
# 1457 passed, 9 skipped, 2 failed (pre-existing, unrelated — see below)

python scripts/export_openapi.py   # docs/api/openapi.json regenerated for
                                    # the /version, /capabilities and
                                    # /learning/experiments contract changes

cd flutter_app && flutter analyze && dart format --output=none --set-exit-if-changed lib test && flutter test
# No issues found!; 140 files already formatted, 0 changed; All tests passed! (182 tests)
```

**Pre-existing failure, not caused by this change (verified: neither file
appears in `git diff --stat origin/main`, and both fail identically in
isolation on an unmodified checkout):** `tests/test_api_tracking.py::test_timeseries_buckets_predictions_by_day`
and `::test_predictions_list_pagination_covers_every_item_once` fail with
a `daily_candidate_scans` unique-constraint collision — a `date.today()`-
relative fixture landing on an already-used `(scan_date, universe_version)`
pair as real calendar time advances. Out of scope for this EPIC; not fixed
here.

**Deliberately deferred, with rationale:**
- True frame-timing performance budgets (startup, transition, scroll
  jank) still require `integration_test` in profile mode against a real
  device/emulator — the same honest gap M1.143 already named, unchanged by
  this session because this harness (`flutter test`, headless widget
  tests) cannot produce that measurement meaningfully.
- No conversion of `MraDenseTable`/card `Column` lists to
  `ListView.builder` — see "Not a gap, verified" above; every such list is
  already bounded by cursor pagination, so virtualizing would be
  optimizing a data structure that is never actually large in memory.
- ETag/Cache-Control was added only to `/version`/`/capabilities` — every
  other endpoint's data is either per-user, per-request-filtered, or
  changes on a timescale (market data, predictions, tracking) where a
  naive cache header would risk serving stale trading-relevant numbers;
  extending caching there needs a real invalidation strategy, not a
  blanket header, and is out of this EPIC's safe-to-do-now scope.
