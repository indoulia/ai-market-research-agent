# EPIC-M3.15 — Longitudinal Tracking & Performance Analytics

**Status:** DONE
**Execution Status:** COMPLETED
**Track:** UI + API
**Priority:** P0

## Objective
Expose how individual predictions and MRA aggregate performance evolve over time, preserving clean historical evidence and making improvement visible.

## UI Scope
- Prediction outcome history.
- Trust trend.
- Hit/SL/expiry distributions.
- Return and benchmark-relative trend.
- Horizon/sector/regime/size/setup breakdowns.
- Prediction revision timeline.
- Filters and date range.
- Compact charts with exact values available on interaction.

## API Contract
`GET /api/v1/tracking/summary`
`GET /api/v1/tracking/timeseries`
`GET /api/v1/tracking/breakdown`
`GET /api/v1/tracking/predictions`

Query:
`from`, `to`, `horizon`, `sector`, `marketCap`, `regime`, `symbol`, `setup`, `page`, `pageSize`.

Responses include:
`metric`, `value`, `sampleSize`, `asOf`, `methodologyVersion`, `benchmark`, `confidence/reliability` where applicable.

## Acceptance Criteria
- Aggregate metrics reconcile with immutable prediction outcomes.
- Time-series points are reproducible.
- Small samples are identified.
- User can drill from aggregate metric to underlying predictions where permitted.
- Mobile and web charts remain legible and compact.

## Completion Report (2026-08-22)

**Context:** see `docs/epics/EPIC-M3-ROADMAP-NOTE.md` — this EPIC is the
combined-roadmap renumbering of the old split track's `M1.146` slot, and
is the last of the M3.1-M3.15 roadmap. As predicted by the task brief,
almost all of this EPIC's scope was already delivered by three prior,
merged EPICs, verified (not reimplemented) below; only two genuine gaps
were found and implemented this session.

### Already satisfied — verified against real, merged code

**EPIC-M1.147 (API) + EPIC-M1.148 (Flutter UI)** — "Longitudinal Tracking
& Performance Analytics", the old split-track version of this exact
EPIC — already built the entire base contract this EPIC names:
- All four exact endpoints this EPIC's API Contract requires already
  exist verbatim: `GET /api/v1/tracking/summary`,
  `GET /api/v1/tracking/timeseries`, `GET /api/v1/tracking/breakdown`,
  `GET /api/v1/tracking/predictions` (`api/routers/tracking.py`,
  `api/services/tracking.py`).
- UI Scope items already fully built by `flutter_app/lib/features/tracking/tracking_screen.dart`
  and friends: prediction outcome history (closed-predictions table +
  drill-down), Trust trend (Trust Score trend chart), hit/SL/expiry
  distributions (`targetHitRate`/`stopLossRate`/`horizonExpiryRate` KPIs),
  return trend (secondary outcome trend chart), horizon/sector/regime
  breakdowns (`_dimensions` chip selector), a date-range quick-select
  (7d/30d/90d/1y).
- Small-sample flagging (`smallSample`, `MIN_SAMPLE_SIZE_FOR_COMPARISON`)
  and drill-down to `RecommendationDetailScreen` were already present.

**EPIC-M3.7 (Performance & Trust Intelligence)** — already added:
- `GET /api/v1/performance/{summary,timeseries,breakdown}` path aliases
  onto the same `api/services/tracking.py` service layer
  (`api/routers/performance.py`).
- `stock` as a breakdown dimension (this EPIC's "size" language in the
  UI Scope breakdown list is covered by the pre-existing `marketCap`
  dimension, not `stock`, but both already existed).
- Benchmark-relative return/alpha (`benchmarkReturn`/`relativeReturn`,
  wired to real M1.129 data).

**EPIC-M3.4 (Recommendation Detail & Prediction Timeline, old M1.135)** —
this EPIC's UI Scope item "Prediction revision timeline" is fully
satisfied by the already-merged `GET /recommendations/{id}/timeline`
(`api/services/recommendation_detail.py::get_timeline`, backed by real
`app.recommendation_revision.get_revision_history`/`compare_versions`)
and its Flutter rendering in `recommendation_detail_screen.dart` /
`timeline_item.dart`. `TrackedPrediction.id` is deliberately
`RecommendationGeneration.id` (M1.148's own finding), so the tracking
screen's existing drill-down
(`context.push('/tracking/recommendation/${p.id}')`) already reaches
this timeline — no new UI or endpoint needed. Immutability is preserved
throughout: this surfaces revision *history*, never rewrites a past
prediction (product constraint respected, unchanged).

### Genuine gaps found and implemented this session

1. **Filters/date-range query surface.** This EPIC's own API Contract
   names `from`, `to`, `horizon`, `sector`, `marketCap`, `regime`,
   `symbol`, `setup` as query parameters, and its UI Scope names
   "Filters and date range" — none of these existed pre-this-session
   (the old contract only had `range`/`metric`/`bucket`/`dimension`/
   `status`/`cursor`/`pageSize`). EPIC-M3.7's own Completion Report had
   explicitly flagged this exact gap as deliberately deferred
   ("genuinely new multi-dimension simultaneous filtering ... would be
   substantial new design surface ... flagging as a real, named gap for
   a dedicated follow-up EPIC") — this session is that follow-up.
   - `api/services/tracking.py`: new `TrackingFilters` dataclass +
     `make_filters()` (validates `horizon` against the product's real
     1-7 trading-day constraint), `_resolve_window()` (an explicit
     `from`/`to` pair overrides `range`; both must be given together),
     `_filtered_rows`/`_regime_lookup`/`_apply_python_filters`/
     `_filtered_prediction_ids` shared helpers. `marketCap`/`regime`/
     `setup` aren't plain columns (computed bucket / a scan-linked
     lookup / "no classification module exists"), so they're applied as
     a second Python-side pass over SQL-filtered rows — the same
     two-pass shape `get_breakdown` already used pre-this-session for
     `marketCap`/`regime`, now shared across all four functions.
     `get_summary`/`get_timeseries` require a resolved window (either
     `range` or `from`+`to`); `get_breakdown`/`list_tracked_predictions`
     keep their pre-existing "whole history unless windowed" default
     when no `from`/`to` is given, so calling any endpoint with zero
     filters reproduces the exact pre-M3.15 query and result set
     (verified: all 26 pre-existing tests in `tests/test_api_tracking.py`
     + `tests/test_api_performance.py` pass unchanged).
     `list_tracked_predictions` constrains its keyset-paginated query
     with an `IN` clause over a pre-computed eligible-id set rather than
     post-filtering fetched pages, so pagination's "every item exactly
     once" guarantee holds under `marketCap`/`regime`/`setup` filters.
   - `api/routers/tracking.py` + `api/routers/performance.py`: every
     endpoint on both routers gained the same `from`/`to`/`horizon`/
     `sector`/`marketCap`/`regime`/`symbol`/`setup` query params via a
     shared `_filters_dep` FastAPI dependency, so `/tracking/*` and
     `/performance/*` behave identically (verified by a new parity
     test).
   - `TrackingSummary.range`/`TimeseriesResponse.range` report `"custom"`
     (not a stale `range_key`) when an explicit `from`/`to` window was
     used, rather than echoing back a range that wasn't what actually
     determined the window.
   - `page`/`pageSize` deviation (named, not silent): this EPIC's doc
     names `page` for `/predictions`, but the platform's own established
     convention — every paginated list in this codebase, including this
     one pre-existing — is keyset cursor pagination
     (`api/pagination.py`, `api/services/keyset.py`). Kept `cursor`/
     `pageSize` unchanged rather than introducing a second, inconsistent
     pagination style for one endpoint; same posture EPIC-M3.7 already
     took for other doc-vs-reality field-naming mismatches.
   - Flutter: new `flutter_app/lib/features/tracking/tracking_filters.dart`
     (`TrackingFilters` value object: `toQuery()`, `activeCount`,
     `copyWith`), threaded through all four `TrackingRepository` fetch
     methods and into `TrackingScreen` as a "Filters" bottom sheet
     (horizon/marketCap/regime `MraFilterBar` chips reusing the exact
     `MraFilterOption`/`MraFilterBar`/`showMraBottomSheet` pattern
     `OpportunityExplorerScreen`'s own filter sheet already established;
     sector/symbol `TextField`s with the same debounced-`onChanged`
     pattern) plus a "Custom…" date-range chip opening
     `showDateRangePicker`. `regime` option values
     (`BULLISH_HIGH_VOL`/`BULLISH_LOW_VOL`/`NEUTRAL_HIGH_VOL`/
     `NEUTRAL_LOW_VOL`/`BEARISH_HIGH_VOL`/`BEARISH_LOW_VOL`) are
     `app/market_regime.py`'s real, fixed trend x volatility
     classification, not a fabricated taxonomy. `setup` has no UI
     control (only one real value, `UNCLASSIFIED`, exists platform-wide)
     but is still supported end-to-end in the API for contract
     completeness.

2. **Interactive charts ("compact charts with exact values available on
   interaction").** EPIC-M1.148's own Completion Report had explicitly
   named this as a known, deferred gap ("No interactive per-point
   tooltips on the trend charts themselves ... the shared `SparklineChart`
   has no hit-testing"). Implemented, not deferred again, this session:
   - `flutter_app/lib/design_system/components/sparkline_chart.dart`:
     `SparklineChart` converted to a `StatefulWidget` with an opt-in
     `interactive`/`pointLabels` mode (default `false`, so every
     pre-existing non-interactive call site — e.g. price-history cards —
     is byte-for-byte unaffected; verified via
     `components_smoke_test.dart` passing unchanged). Tap/drag/hover
     resolves the nearest point via `LayoutBuilder` + `GestureDetector`/
     `MouseRegion`, highlights it on the painted line, and reveals its
     pre-formatted label above the chart.
   - `flutter_app/lib/features/tracking/tracking_trend_card.dart`: both
     trend charts (Trust Score, secondary outcome) now pass
     `interactive: true` with per-point labels
     (`"<value> · <bucket date> (n=<sampleCount>)"`) — exact values on
     interaction, without any new chart-painting code or a second
     charting approach (still the one shared `SparklineChart`).

### Tests (TDD)

- `tests/test_api_tracking.py` — 9 new tests: `from`/`to` overriding
  `range` (+ `range: "custom"`), `from` without `to` rejected, `horizon`
  narrowing (two genuinely distinct horizons via `atr_percent`, not a
  mutation of an immutable `Prediction` field — confirmed
  `RecommendationImmutableError` fires on a direct attempt, which is
  correct, existing platform behavior), invalid horizon (9) rejected,
  `sector`/`symbol` filters on `/summary`, `marketCap` filter on
  `/breakdown` (including the honest empty-list case), `symbol`/
  `horizon` filters on `/predictions`, `setup` filter matching only
  `UNCLASSIFIED`. One pre-existing behavior tightened as a genuine,
  verified bug found while adding the last test: `dimension=setup`
  now returns an empty `items: []` (not a phantom
  `predictionCount: 0` bucket) when nothing matches, consistent with
  every other dimension's empty-result shape.
- `tests/test_api_performance.py` — 1 new parity test confirming the
  `symbol` filter produces identical output through `/performance/summary`
  and `/tracking/summary`.
- `flutter_app/test/features/tracking/tracking_filters_test.dart` (new) —
  `TrackingFilters`'s `toQuery`/`activeCount`/`copyWith`/`isEmpty` logic.
- `flutter_app/test/features/tracking/tracking_repository_test.dart` —
  3 new tests: every filter forwarded as a query param, filters omitted
  when unset, `/predictions` forwarding `symbol`/`horizon`.
- `flutter_app/test/features/tracking/tracking_screen_test.dart` — 6 new
  tests: Filters button active-count label, horizon filter refetch,
  market-cap filter refetch, debounced symbol-filter refetch, "Clear all
  filters", and tapping the interactive trend chart revealing an exact
  point value.

**Validation run:**
```
python -m pytest tests/test_api_tracking.py tests/test_api_performance.py -q
# 26 passed

python -m pytest -q
# 1469 passed, 9 skipped -- full existing suite, zero regressions

cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && dart format --output=none --set-exit-if-changed lib test
# Formatted 147 files (0 changed)

cd flutter_app && flutter test
# 212 tests passed, All tests passed!
```

`docs/api/openapi.json` regenerated via `PYTHONPATH=. python
scripts/export_openapi.py` so the new filter query params on all seven
`/tracking/*` + `/performance/*` GET endpoints are in the committed
contract artifact.

### Deliberately not done (rationale)

- **A second Flutter screen or repository for `/performance/*`** — not
  built, same rationale EPIC-M3.7 already established: the existing,
  merged, tested `TrackingScreen`/`TrackingRepository` continue to call
  `/tracking/*`; `/performance/*` exists for this EPIC's own API
  Contract naming, for any other caller.
- **`page`/`pageSize` numeric pagination for `/predictions`** — this
  EPIC's doc names `page`, but every paginated endpoint in this codebase
  (including this one, pre-existing) uses keyset cursor pagination.
  Named, not silent: see the "Genuine gaps" section above.
- **A `setup`/strategy-pattern breakdown taxonomy** — still no such
  classification module exists anywhere in this platform (unchanged
  from EPIC-M1.147/M3.7's own honest gap); the `setup` filter/dimension
  continues to return only the single, honest `UNCLASSIFIED` bucket.
- **Statistical significance/confidence intervals on any rate** — still
  a `smallSample` floor-based flag, not a confidence interval (M1.122,
  unimplemented, unchanged from every prior EPIC in this area).

### Conclusion

EPIC-M3.15's UI Scope and API Contract were ~85% already satisfied by
the existing, merged EPIC-M1.147/M1.148 (base contract + screen),
EPIC-M3.7 (`/performance/*` aliases, `stock` dimension, benchmark
data) and EPIC-M3.4 (prediction revision timeline) work. The two
genuine, previously-named gaps — the `from`/`to`/dimension filter query
surface, and interactive "exact value on interaction" charts — have
been implemented, tested and verified above. Marking this EPIC `DONE`.
This is the last EPIC in the M3.1-M3.15 roadmap.
