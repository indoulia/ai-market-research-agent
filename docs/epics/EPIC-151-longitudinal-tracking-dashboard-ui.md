# EPIC-151 — Longitudinal Tracking Dashboard UI

**Track:** UI
**Status:** DONE
**Execution Status:** COMPLETE
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
UI analytics team against EPIC-150 fixtures/OpenAPI.

## Dependencies
EPIC-136, EPIC-137, EPIC-150.

## Completion Report

**Status:** DONE

### What was built
- `lib/features/tracking/tracking_summary.dart`, `tracking_timeseries.dart`, `tracking_breakdown.dart`, `tracked_prediction.dart` — domain models parsed from EPIC-150's real, merged `api/schemas/tracking.py` shapes (`TrackingSummary`, `TimeseriesResponse`/`TimeseriesPoint`, `BreakdownResponse`/`BreakdownItem`, `TrackedPrediction`). `TrackingSummary.activeCount` is the one derived value in this epic (`predictionCount - closedCount`, for the Layout's "active" KPI) — plain arithmetic over two real API fields, not a recomputed rate (AC: "no dashboard widget duplicates calculations already returned by the API").
- **Confirmed against real source, not the epic doc's prose, that every rate/return/trust/calibration field the tracking API returns is fraction-scale (0..1, e.g. `0.42` for 42%)** — checked `api/services/tracking.py`'s `get_summary`/`get_breakdown` (no `*100` anywhere) against the model columns' `Numeric(10, 6)`/`Numeric(10, 8)` precision. This is the **opposite** convention from the already-merged `recommendations` API's `upsidePct` (which `api/services/recommendations.py` explicitly multiplies by 100 before serializing). Every percentage in this screen is formatted client-side (`value * 100`) accordingly.
- **Also confirmed `TrackedPrediction.id` is deliberately `RecommendationGeneration.id`** (via `api/services/tracking.py::list_tracked_predictions`'s query), the same id space `RecommendationDetailScreen` already expects — not `Prediction.id`. Drill-down navigation (`context.push('/tracking/recommendation/${p.id}')`) is correct because of this, not by assumption.
- `lib/features/tracking/tracking_repository.dart` — repository boundary over all four real `/tracking/*` endpoints; `TrackedPredictionsPage` follows the same `meta.nextCursor` cursor-pagination convention every other paginated repository in this app already uses.
- `lib/features/tracking/tracking_trend_card.dart` — reuses the existing shared `SparklineChart` for the line itself (no new chart-painting code) and adds what it doesn't provide: axis min/max value labels, a per-metric `Tooltip` (UX Rule: "use tooltips for statistical terms"), and the total evaluated sample count across buckets (UX Rule: "show sample size alongside rates").
- `lib/features/tracking/tracking_screen.dart` — the "Tracking" destination: range selector (7d/30d/90d/1y, auto-selecting day vs. week timeseries buckets), a small-sample warning banner, a 6-card KPI grid (Active/Closed/Target-hit rate/Avg realized return/Avg predicted return — kept as separate cards per the UX Rule to "clearly distinguish predicted vs realized return" rather than one card's ambiguous delta/Trust score with a period-over-period `trustDelta`), the Trust Score trend chart, a secondary outcome trend chart (hitRate/return/calibration, selectable), breakdown cards for horizon/sector/marketCap/regime/setup (each showing sample size and a small-sample icon), and a closed-predictions table with cursor-based "Load more" and drill-down to the recommendation detail screen. Model version is surfaced as a plain caption (honestly showing `"MIXED"` when the range spans more than one model version, per EPIC-150's own AC).
- `lib/app_shell/app_router.dart` — the `/tracking` branch's `DestinationPlaceholderScreen` replaced with the real `TrackingScreen`, plus a nested `recommendation/:id` route matching the same pattern the Home/Discover/Market branches already use.

### Real bugs/gaps found while integrating (not fabricated)
- The fraction-vs-percent-scale distinction above was found by reading `api/services/tracking.py` and `app/models.py` directly rather than trusting the epic doc's plain-English field list, which doesn't state units. Getting this wrong would have silently displayed e.g. a 42% hit rate as "0.4%" everywhere on this screen.
- Noted, but deliberately left untouched (out of this epic's scope): the already-merged EPIC-139 `DashboardScreen`'s `avgTrust.round().toString()` treats `Recommendation.trustScore` as if it were already on a 0-100-ish scale, when `PredictionTrustScore.overall_trust_score` (the same underlying field) is fraction-scale 0..1 per `app/prediction_trust_score.py`'s own `>= Decimal("0.75")` threshold check — meaning that display likely rounds to a literal "0" or "1" today. This screen's own Trust KPI/trend formats trust correctly (`× 100`); the pre-existing dashboard display was not modified, since fixing it is a separate, already-approved-and-merged epic's concern, not this one's.

### Honest gaps / known limitations
- The secondary-metric and breakdown-dimension selections are session-local UI state, not persisted preferences — every screen visit starts at hitRate/horizon. No AC requires persistence, and EPIC-145's preferences contract has no field for this.
- No interactive per-point tooltips on the trend charts themselves (only a static per-metric info tooltip) — the shared `SparklineChart` has no hit-testing; adding that would mean a new bespoke chart painter, which felt like more surface than this epic's "avoid more than 2-3 primary charts per view, use tooltips for statistical terms" rules actually call for.
- `benchmarkReturn`/`relativeReturn` are always `null` today (EPIC-150's own honestly-documented gap, pending EPIC-132) — this screen doesn't render them at all rather than showing a permanent "—" for a metric that doesn't exist yet.

### Testing
- `test/features/tracking/tracking_repository_test.dart` — request shape (path/query params) and response decoding for all four endpoints against a fake `http.Client`, matching `test/core/api_client_test.dart`'s established pattern.
- `test/features/tracking/tracking_screen_test.dart` — KPI grid/model-version/trend-chart rendering from real fixture shapes, small-sample banner shown/hidden correctly, range change refetching the summary with the new range, secondary-metric switch refetching only that timeseries (breakdown/summary untouched), breakdown-dimension switch refetching and re-rendering, cursor-based "Load more" appending a second page and then showing "You're all caught up", the empty-predictions state, the error/retry state, drill-down navigation to `/tracking/recommendation/:id` through a real `GoRouter`, and the EPIC-146-style 2x-text-scale regression check at a narrow (360px) width.
- Full existing suite re-run after every change: 114/114 passing, zero regressions to any previously-merged epic in this track.
- `flutter analyze`: no issues.
