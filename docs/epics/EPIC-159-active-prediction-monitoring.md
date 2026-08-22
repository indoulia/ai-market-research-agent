# EPIC-159 — Active Prediction Monitoring

**Status:** DONE
**Execution Status:** COMPLETED
**Track:** UI + API
**Priority:** P0

## Objective
Give users a compact live view of active positive recommendations and their current distance to target, stop-loss and horizon expiry.

## UI Scope
- Active recommendation grid/list.
- Current price, target, SL, distance-to-target, distance-to-SL.
- Horizon remaining.
- Trust and freshness.
- Last event/revision indicator.
- Target-hit and SL-hit transition states.
- Compact progress visualization.
- User-selectable refresh behavior with server freshness.

## API Contract
`GET /api/v1/predictions/active`
`GET /api/v1/predictions/active/{predictionId}`

Response:
`predictionId`, `symbol`, `price`, `targetPrice`, `stopLoss`, `horizon`, `remainingTradingDays`, `distanceToTargetPercent`, `distanceToStopLossPercent`, `score`, `confidence`, `trustScore`, `status`, `lastPriceAt`, `lastRevisionAt`, `nextEvaluationAt`.

## Acceptance Criteria
- Active state is sourced from EPIC-122, not recomputed differently in Flutter.
- Target/SL closure appears consistently after outcome confirmation.
- Stale data is clearly indicated.
- No user-facing negative recommendation states are introduced.

## Completion Report (2026-08-22)

**Branching context:** based directly on `origin/main` (`f754ebf`, which
already includes EPIC-156 via PR #268). `autonomous/epic-m3-6` and
`autonomous/epic-m3-7` had no remote branch or PR at the time this EPIC's
branch (`autonomous/epic-m3-8`) was created or when its PR was opened —
per this EPIC's own branching instructions, no rebase-onto-sibling-EPIC
step was needed either before starting or before opening the PR.

**What already existed (verified, not reimplemented):**
- `app/prediction_outcome_monitor.py` (EPIC-122, merged PR #235) is
  the exact source-of-truth this EPIC's AC calls for: `PredictionOutcomeEvent`
  rows (`ACTIVE`/`TARGET_HIT`/`STOP_LOSS_HIT`/`HORIZON_EXPIRED`/
  `INVALIDATED`/`DATA_UNRESOLVED`), `get_target_stop_prices` (the one
  canonical absolute target/stop-loss derivation), `get_terminal_event`/
  `get_event_history`. EPIC-122's own completion report explicitly named
  "wiring an actual scheduled/API consumer" as left to a future EPIC —
  this is that EPIC.
- `api/routers/recommendations.py`/`api/services/recommendations.py`
  (EPIC-138) already define the "live feed" eligibility this EPIC
  reuses verbatim: latest included `PositiveOpportunityRanking` batch +
  `RecommendationLifecycle.state in OPEN_STATES` (EPIC-018).
- `app/market_calendar.py` (EPIC-124, `count_trading_days`,
  `get_holiday_dates_in_range`) and `app/schedule_orchestration.py`
  (EPIC-121, `classify_session`, `OPERATION_PRICE_MONITORING`'s 15-
  minute cadence) — both landed after EPIC-140 was written (that EPIC's own
  docstring says its `expiryAt` is "a naive calendar-day estimate ...
  since EPIC-124 hasn't landed") and are reused here for a real,
  trading-day-aware `remainingTradingDays` and an honest
  `nextEvaluationAt` estimate.
- `app/recommendation_revision.get_revision_history` (EPIC-050) for
  `lastRevisionAt`.
- Flutter design-system components reused as-is: `MraCard`, `MraChip`,
  `MraStateView`, `SkeletonCard`, `showMraBottomSheet`, `MraTypography`,
  `MraColorScheme` (all EPIC-136).
- No pre-existing UI screen already covered this: EPIC-139's dashboard
  cards show target/SL as static prices only (no live distance/progress/
  horizon-remaining/status), and EPIC-150/148's "Tracking" screen is a
  historical predicted-vs-realized track record, not a live monitor.

**Genuine gaps implemented this session:**
- `api/schemas/predictions_active.py` — the compact `ActivePrediction` DTO
  matching the EPIC's literal response field list, plus `companyName`/
  `exchange` (needed for any real UI to identify the row; not otherwise
  in the literal list).
- `api/services/predictions_active.py` — `list_active_predictions`/
  `get_active_prediction`: joins the same EPIC-138 eligibility query,
  enriches each row with EPIC-122's `status` (read-only — this API layer
  never calls `evaluate_prediction_realtime` itself, matching the
  existing read-only convention in `recommendation_detail.get_outcome`),
  `get_target_stop_prices`-derived distances, `count_trading_days`-based
  `remainingTradingDays`, and `nextEvaluationAt`. Extensive module
  docstring names every inherited limitation explicitly (read-only
  staleness, revision-identity edge case inherited from EPIC-138's own list
  query).
- `api/routers/predictions_active.py` — `GET /api/v1/predictions/active`
  (cursor-paginated, same keyset convention as `/recommendations`) and
  `GET /api/v1/predictions/active/{predictionId}` (404 via the existing
  `NotFoundError` convention), wired into `api/app.py`.
- `docs/api/openapi.json` regenerated (`python scripts/export_openapi.py`).
- Flutter: `flutter_app/lib/features/tracking/active_prediction.dart`
  (domain model + `ActivePredictionStatus` constants mirrored verbatim
  from `app.prediction_outcome_monitor`), `active_prediction_card.dart`
  (compact card: price, target/SL with % distance, a `LinearProgressIndicator`-based
  compact progress bar between stop-loss and target colored by status,
  horizon-remaining, Trust, "Priced Xm ago"/"Revised Xm ago" freshness
  text, status chip covering every EPIC-122 state). `tracking_repository.dart`
  gained `fetchActivePredictions`/`fetchActivePrediction`. `tracking_screen.dart`
  gained an "Active positions" section (placed above the existing
  historical charts) with: a user-selectable auto-refresh cadence
  (Off/30s/1m/5m, default Off — a live feed opts a user IN to polling),
  a manual refresh button, "Updated Xm ago" section-level freshness, a
  responsive 1/2/3-column card grid, cursor-based "Load more", and
  tap-to-open a bottom sheet that always re-fetches
  `/predictions/active/{predictionId}` fresh (falling back to the list's
  already-known snapshot, clearly labeled, if that re-fetch fails) —
  demonstrating both endpoints are genuinely consumed, not just defined.
  Placed inside the existing "Tracking" destination (not a new bottom-nav
  destination) since it is a live-monitoring slice of the same
  active/closed prediction universe that screen already partitions.

**Tests (TDD):**
```
python -m pytest tests/test_api_predictions_active.py -q
# 11 passed — empty feed, full-field mapping, lifecycle-closed exclusion,
# EPIC-122 TARGET_HIT/STOP_LOSS_HIT status (not recomputed), price-relative
# distance math, cursor pagination across sectors, detail 200/404,
# detail staying correct after lifecycle closure, missing-MarketPrice
# edge case (None fields, no crash).

python -m pytest -q
# 1400 passed, 9 skipped in 163.72s — full existing suite, no regressions
# (includes docs/api/openapi.json freshness check).

cd flutter_app && flutter analyze
# No issues found!

cd flutter_app && flutter test
# All tests passed! (155 tests, incl. 5 new "EPIC-159 active positions
# section" cases in tracking_screen_test.dart: empty state, full card
# rendering, EPIC-122-sourced status label, fresh-refetch-on-tap detail
# sheet, periodic-refresh-interval polling)

cd flutter_app && dart format --set-exit-if-changed .
# Formatted 118 files (0 changed) -- clean.
```

**Real bugs found and fixed during implementation:**
- `_remaining_trading_days` crashed (`ValueError: end_date must not be
  before start_date`) whenever "today" (real wall-clock `datetime.now()`)
  was earlier than a prediction's `as_of` — an edge case every test
  fixture in this codebase hits by convention (fixtures anchor on a
  fixed future `AS_OF`, e.g. `datetime(2027, 1, 1)`). Fixed by treating
  "today at or before entry date" as zero elapsed trading days (the full
  horizon remains) instead of calling `count_trading_days` with an
  invalid range.
- The card's SL/Target `Row` (`mainAxisAlignment: spaceBetween`, no
  `Expanded`) overflowed at ordinary card widths once real percentage
  text was substituted in — fixed by wrapping both sides in `Expanded`
  with ellipsis, matching this codebase's established overflow-safety
  convention used everywhere else in the design system.
- Adding the new section pushed the pre-existing "Realized return" chip
  below the fold in `tracking_screen_test.dart`'s "switching the
  secondary metric" test; fixed by adding the same `tester.ensureVisible`
  call the sibling "Sector" test already used, not by shrinking new
  content.

**Deliberately deferred, with rationale:**
- `nextEvaluationAt` is a best-effort estimate (next
  `OPERATION_PRICE_MONITORING`-cadence tick during a live session, or
  next trading-day open otherwise) — no scheduler is actually wired to
  call `evaluate_prediction_realtime` in production yet (EPIC-122's own
  completion report already named this gap); this field documents when
  new data *could* next move the status, not a guarantee a job will run
  then.
- `lastRevisionAt`/ranking-score resolution inherits the same
  no-`get_active_version`-resolution characteristic EPIC-138's own
  `/recommendations` list already has (both query `PositiveOpportunityRanking`/
  `Prediction` directly rather than resolving through the revision
  chain first) — a pre-existing, platform-wide characteristic, not a new
  gap introduced by this EPIC; fixing it is a cross-cutting concern
  broader than EPIC-159's scope.
- No new bottom-nav destination was added; "Active positions" was placed
  inside the existing "Tracking" screen (see rationale above) rather than
  claiming a fresh slot in `kAppDestinations`, avoiding unrelated changes
  to app-shell navigation/tests.
- `flutter_app/tool/mock_api_server.dart` (a manual local dev-server
  script, not exercised by any automated test — it does not even cover
  the already-`DONE` `/tracking/*` contracts) was not extended with the
  new routes; out of scope and zero test impact either way.

**Conclusion:** EPIC-159's UI scope and both named API endpoints are
implemented, tested and wired end-to-end, composing entirely from
already-merged domain modules (EPIC-018/EPIC-050/EPIC-118/EPIC-121/EPIC-122/EPIC-124/
EPIC-136/EPIC-138) per the EPIC's own AC. Marking this EPIC `DONE`.
