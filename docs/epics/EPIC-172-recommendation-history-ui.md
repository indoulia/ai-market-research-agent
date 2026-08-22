# EPIC-172 — Recommendation History UI (`/history` destination)

**Status:** DONE
**Execution Status:** COMPLETED
**Source:** Self-approved delta (no GitHub issue) per the standing `project_post_epic_deployment_validation`
delegation — merged via PR #303, commit `615ccc0`. Retroactively documented and renumbered into the
canonical `docs/epics/EPIC-NNN-*.md` sequence on 2026-08-22 (was informally labeled "EPIC-M3.17" in
source comments only, which collided with the unrelated, later Marksy-branding issue #300 that also
self-titled itself "EPIC-M3.17" — see [[feedback_keep_epic_numbers_in_canonical_sequence]] memory for
why every epic now gets a real, collision-free number).
**Track:** Flutter UI
**Priority:** MEDIUM
**Product:** MRA / Marksy

## Objective

Wire the app shell's left-nav "History" destination to a real screen. It previously rendered a
generic placeholder mislabeled as owned by EPIC-148 (old numbering: EPIC-M1.138), but that epic only
ever built the per-recommendation detail/history view — no top-level history list existed.

## What shipped

- `flutter_app/lib/features/history/history_screen.dart` — a focused, full-page list of resolved
  (closed) recommendations, reusing the already-merged `/tracking/predictions?status=closed` data
  layer (`TrackingRepository`/`TrackedPrediction`/`TrackingFilters`) as-is; no backend changes needed.
- Extracted `TrackingScreen`'s filter-sheet body and closed-predictions table into shared widgets
  (`tracking_filters_sheet.dart`, `closed_predictions_table.dart`) so `TrackingScreen` and
  `HistoryScreen` render identical filter/table UI instead of a drift-prone second copy.
- Deleted the now-fully-dead `DestinationPlaceholderScreen` — every app-shell destination is real.
- `app_destination.dart`'s `/history` entry now reads `ownerEpic: 'EPIC-172 Recommendation History UI'`
  (previously the collision-causing informal `'EPIC-M3.17 Recommendation History UI'`).

## Tests

`flutter_app/test/features/history/history_screen_test.dart` (new, per PR #303).

**Validation run (from PR #303):** `flutter analyze` clean, `dart format` clean, full `flutter test`
suite passing.
