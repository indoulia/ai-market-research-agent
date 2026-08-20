# EPIC-M1.36 — Longitudinal Recommendation Tracking

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Track every recommendation from issuance through its selected horizon using immutable daily observations.

## Scope
- Record recommendation entry state.
- Capture daily price/return observations.
- Track progress against horizon.
- Preserve original score, probability, horizon, model, and data snapshot.
- Record interim status without overwriting prior observations.
- Support 1/3/5/7-day tracking where applicable.

## Acceptance Criteria
- [ ] Every issued recommendation has a tracking lifecycle.
- [ ] Daily observations are immutable and timestamped.
- [ ] Original recommendation attributes never change retrospectively.
- [ ] Tracking handles missing market data explicitly.
- [ ] Horizon completion is deterministic.
- [ ] Historical tracking can be reconstructed for any recommendation.

## Dependencies
**Previous:** M1.15, M1.35
**Next:** M1.37, M1.38

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.36

### Branch

autonomous/epic-m1-36, branched cleanly from `main` (both declared dependencies -- M1.15 and M1.35 -- are already merged).

### Objective

Track every issued recommendation from issuance through its selected horizon via an immutable daily observation trail, distinct from M1.5/M1.15/M1.21's single terminal-outcome computation.

### Design Decisions

- **New table `recommendation_observations`** (migration `0025`, chains off M1.35's `0024`): one immutable row per `(prediction_id, day_number)` (unique constraint), append-only, never updated once created (`before_update` guard, `RecommendationObservationImmutableError`).
- **Genuinely new capability, not a duplicate of M1.5/M1.15/M1.21**: those compute one final outcome for the whole horizon window (highest/lowest/closing price, target/stop hit) once the horizon completes. This module additionally records the *day-by-day* trajectory during that window -- day 1's close/return, day 2's, and so on -- so a recommendation's progress can be reconstructed at any point in time, not only its terminal result.
- **`record_daily_observations(session, prediction)`** mirrors M1.15's point-in-time, idempotent, resumable pattern, applied per day instead of once: it queries `MarketPrice` rows after `prediction.as_of_timestamp`, and for each trading day up to (and including) `prediction.horizon_days` that doesn't already have an observation, records one. A day whose data hasn't arrived yet simply isn't created until a later call finds it (proven by `test_resuming_adds_only_new_days_without_touching_prior_ones`); a day beyond the horizon is never observed at all (proven by `test_never_observes_beyond_the_horizon`).
- **Missing/invalid market data is explicit, not fabricated or silently skipped** (AC: "tracking handles missing market data explicitly"): the same OHLC-validity check `app/outcomes.py` already uses (reimplemented locally here rather than importing that module's private helper, per this platform's established convention) marks a day `data_available=False` with `close_price`/`return_since_entry` both `None`, while day numbering continues correctly for subsequent valid days.
- **Horizon completion is deterministic** (AC): `horizon_complete=True` if and only if `day_number == prediction.horizon_days` -- a single, unambiguous condition, not inferred from any other state.
- **"Preserve original score, probability, horizon, model, and data snapshot" (scope) required no new code**: `Prediction` is already immutable (M1.13's own guard); this module only ever reads it.
- **"Every issued recommendation has a tracking lifecycle" (AC)** holds because `record_daily_observations` accepts any `Prediction` and works identically regardless of which EPIC issued it (M1.13/M1.17/M1.19/M1.33) -- there is no separate "start tracking" step to forget to call.

### Files Changed

- `app/recommendation_tracking.py` — new: `record_daily_observations`, `get_recommendation_tracking_history`, `RecommendationObservationImmutableError`, `OBSERVATION_RULE_VERSION`.
- `app/models.py` — new `RecommendationObservation` model.
- `migrations/versions/0025_recommendation_observations.py` — new migration.
- `tests/test_recommendation_tracking.py` — new: 7 tests.
- `docs/epics/EPIC-M1.36-longitudinal-recommendation-tracking.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_recommendation_tracking.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0025_recommendation_observations`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0024` through `0025` (verified `recommendation_observations` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results (sample historical reconstruction included)

- `pytest -q`: **312 passed, 0 failed** (305 pre-existing from `main` + 7 new).
- `pytest -v tests/test_recommendation_tracking.py`: **7 passed** — a full 5-day horizon produces exactly one observation per day with the correct close price/return, and only the final day marked `horizon_complete`; a partial 2-of-5-day window observes only what's available, none complete; resuming after 3 more days arrive adds exactly those 3 new observations without touching the first 2, and a full reconstruction via `get_recommendation_tracking_history` shows all 5 days `[1, 2, 3, 4, 5]` in order (the sample historical reconstruction this EPIC's Completion Report format calls for); a 3-day horizon with 5 days of available data never observes days 4-5; a middle day with invalid OHLC is recorded `data_available=False` with no fabricated price while the valid day before and after it are recorded normally; and a direct mutation attempt after creation raises `RecommendationObservationImmutableError`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Every issued recommendation has a tracking lifecycle (works for any `Prediction`, from any issuing EPIC).
- [x] Daily observations are immutable and timestamped (`observation_date`, `before_update` guard).
- [x] Original recommendation attributes never change retrospectively (no write path to `Prediction`).
- [x] Tracking handles missing market data explicitly (`data_available=False`, no fabricated values).
- [x] Horizon completion is deterministic (`day_number == horizon_days`, single condition).
- [x] Historical tracking can be reconstructed for any recommendation (`get_recommendation_tracking_history`, proven by test).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct sample reconstruction test. This EPIC's day-by-day trajectory is a genuinely new capability layered on top of, not duplicating, M1.5/M1.15/M1.21's single terminal-outcome mechanism. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->