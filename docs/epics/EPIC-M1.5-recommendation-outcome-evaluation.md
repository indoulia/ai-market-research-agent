# EPIC-M1.5 — Evaluate Recommendation Outcomes

**Status:** VALIDATING
**Priority:** P1

## Objective

Automatically determine whether each completed positive recommendation succeeded using its predefined horizon and objective market-price outcome rule.

## Dependencies

- M1.4 — Persist Recommendation History

## Scope

1. Evaluate completed 1/3/5/7 trading-day recommendations.
2. Capture the objective evaluation price and actual return.
3. Classify each recommendation deterministically as SUCCESS, FAILURE, or UNEVALUABLE.
4. Record predicted versus actual return and prediction error.
5. Ensure the original recommendation remains unchanged.
6. Add focused tests for horizon calculation, market outcomes, and boundary cases.

## Acceptance Criteria

- [ ] Completed recommendations are evaluated at the correct trading-day horizon.
- [ ] Actual return is calculated deterministically.
- [ ] SUCCESS/FAILURE/UNEVALUABLE classification follows a documented rule.
- [ ] Predicted versus actual return is stored.
- [ ] Original recommendation data is immutable.
- [ ] Tests cover all supported horizons and edge cases.

## Non-goals

- Performance dashboards.
- Model retraining.
- Watchlist workflow.
- UI/dashboard work.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.5

### Parent EPIC

None.

### Pull Request

To be recorded once opened (see branch below); this report does not merge itself — per the current contract, Claude opens the PR but does not merge it.

### Branch

autonomous/epic-m1-5

### Implementation Commit

8f29e02

### Objective

Deterministically evaluate each completed recommendation (from M1.4) at its predefined 1/3/5/7 trading-day horizon using only objective market-price data, classify it SUCCESS/FAILURE/UNEVALUABLE, and record predicted-vs-actual return and prediction error, without altering the original recommendation.

### Implemented

- Extended the existing (previously unused) `prediction_outcomes` table/`PredictionOutcome` model — which already had `evaluation_date`, `highest_price`, `lowest_price`, `closing_price`, `maximum_return`, `maximum_drawdown`, `target_hit`, `stop_hit`, `outcome` — with two new required columns, `actual_return` and `prediction_error`, since the scaffold already matched this EPIC's shape (mirrors the M1.4 decision to extend `predictions` rather than duplicate a table).
- Added `app/outcomes.py`:
  - `evaluate_recommendation(session, prediction)` — the core deterministic evaluator. **Documented rule** (since the EPIC required one but did not fully specify it):
    1. **Completion check**: a recommendation is "completed" once at least `horizon_days` `MarketPrice` sessions exist strictly after `as_of_timestamp` for that stock. If fewer exist, the function returns `None` — not yet eligible for evaluation (distinct from `UNEVALUABLE`).
    2. **Window**: the first `horizon_days` sessions after `as_of_timestamp` form the holding-period window.
    3. **Data-quality gate**: if any row in the window fails basic OHLC sanity (non-positive price/volume, or `high`/`low` outside the OHLC envelope — the same invariants M1.2's quality rules use), the recommendation is classified `UNEVALUABLE`. This directly enables M1.6's requirement to exclude unevaluable recommendations from success-rate denominators while still reporting them.
    4. **Exit determination** (bracket-style, day-by-day in chronological order): on each day, check the stop-loss threshold (`entry_price * (1 + stop_return)`) against that day's low **before** the profit target (`entry_price * (1 + target_return)`) against that day's high — daily OHLC can't reveal true intraday sequencing, so checking stop-loss first is the documented, conservative, deterministic convention used here. The first day-level trigger determines the exit price and day. If neither triggers by the end of the window, exit is at the window's last close.
    5. **Classification**: target hit → `SUCCESS`; stop hit (and target not hit that same day) → `FAILURE`; neither hit → `SUCCESS` if the close-based `actual_return` is positive, else `FAILURE`.
    6. `actual_return = (exit_price - entry_price) / entry_price` (exactly equals `target_return`/`stop_return` when a threshold is hit); `prediction_error = actual_return - target_return`.
    7. On success, transitions `prediction.status` from `"OPEN"` to `"EVALUATED"` — the exact transition M1.4 deliberately left `status` mutable for.
  - Raises `RecommendationAlreadyEvaluatedError` if a `PredictionOutcome` already exists for the prediction (evaluation is one-shot; `prediction_id` is unique).
  - A SQLAlchemy `before_update` listener enforcing full immutability on `PredictionOutcome` once created (all fields, no mutable-lifecycle exception needed here) — outcomes are objective historical fact per the top-level contract's "never rewrite historical predictions after outcomes are known," extended here to the outcome record itself, not just the original recommendation.
- Added migration `0006_outcome_actual_return` adding `actual_return`/`prediction_error` (`Numeric(10,6)`, not null) to `prediction_outcomes`.
- Added `tests/test_outcome_evaluation.py` (14 tests, the horizon check parametrized over 4 values): all 4 supported horizons, not-yet-completed, target-hit, stop-hit, same-day tie-break, no-hit-positive-close, `UNEVALUABLE` on bad data, status transition, double-evaluation rejection, outcome immutability, and original-recommendation immutability under evaluation.
- Applied the same narrow, already-established SQLite-portability fix from M1.4 (`BigInteger().with_variant(Integer, "sqlite")`) to `PredictionOutcome.id` and `MarketPrice.id`, since both are now written to directly by this EPIC's SQLite-fixture tests and were blocked by the same dialect quirk documented in M1.4.

### Files Changed

- `app/models.py` — added `PredictionOutcome.actual_return`/`.prediction_error`; sqlite-compatible variant for `PredictionOutcome.id` and `MarketPrice.id`.
- `app/outcomes.py` — new: deterministic outcome evaluation, classification, and immutability enforcement.
- `migrations/versions/0006_outcome_actual_return.py` — new: adds the two `prediction_outcomes` columns.
- `tests/test_outcome_evaluation.py` — new: 14 tests (parametrized horizon check counts as 4) covering all horizons and edge cases.
- `docs/M1-STATUS.md` — reflects M1.5 as implemented; next task is M1.6.
- `docs/epics/EPIC-M1.5-recommendation-outcome-evaluation.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- Migration validation against a disposable scratch Postgres database (`market_agent_epic_m1_5_check`, created and dropped for this validation only): `0001_initial` → `0002_upstox_instrument_key` for real, `alembic stamp 0003_market_price_dedupe` to skip the pre-existing broken migration documented in EPIC-M1.4, then `alembic upgrade head` (runs `0004`, `0005`, and the new `0006` for real), verified the two new columns via `information_schema.columns`, then `alembic downgrade -1` and re-verified they were removed cleanly.

### Test Results

- `pytest -q`: **34 passed** (20 pre-existing after M1.4 + 14 new in `tests/test_outcome_evaluation.py`), 2.16s.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration `0006` upgrade: applied cleanly; `actual_return` and `prediction_error` present as `numeric(10,6)`, `is_nullable='NO'`.
- Migration `0006` downgrade: applied cleanly; both columns removed, all other columns intact.

### Acceptance Criteria

- AC-1 "Completed recommendations are evaluated at the correct trading-day horizon": PASS. Evidence: `test_evaluates_at_correct_trading_day_horizon` (parametrized over 1/3/5/7) asserts the evaluation lands on exactly the `horizon_days`-th session after `as_of_timestamp`, ignoring later sessions; `test_returns_none_when_horizon_not_yet_elapsed` confirms recommendations aren't evaluated early.
- AC-2 "Actual return is calculated deterministically": PASS. Evidence: `test_target_hit_classifies_success_with_exact_actual_return` and `test_stop_hit_classifies_failure_with_exact_actual_return` assert `actual_return` equals exactly `target_return`/`stop_return` on a threshold hit; `test_no_threshold_hit_uses_closing_return_sign` asserts the close-based fallback computation.
- AC-3 "SUCCESS/FAILURE/UNEVALUABLE classification follows a documented rule": PASS. Evidence: the rule is written out step-by-step above (and as comments in `app/outcomes.py`); `test_stop_checked_before_target_on_same_day` specifically exercises and documents the tie-break convention; `test_invalid_price_data_in_window_is_unevaluable` exercises the `UNEVALUABLE` path.
- AC-4 "Predicted versus actual return is stored": PASS. Evidence: `PredictionOutcome.actual_return` stores the actual realized return; `prediction.target_return` (already persisted by M1.4) is the predicted return; `prediction_error = actual_return - target_return` is stored directly for M1.6 to consume without recomputation.
- AC-5 "Original recommendation data is immutable": PASS. Evidence: `test_original_recommendation_is_unchanged_by_evaluation` asserts `entry_price`/`target_return` are untouched after evaluation; M1.4's existing immutability listener on `Prediction` still rejects changes to those fields — only `status` moves, as designed.
- AC-6 "Tests cover all supported horizons and edge cases": PASS. Evidence: 14 tests in `tests/test_outcome_evaluation.py`, covering all 4 horizons, not-yet-completed, target/stop hit, same-day tie-break, no-hit-positive, bad-data/`UNEVALUABLE`, status transition, double-evaluation, and both immutability guarantees.

### Validation

Ran the real local test suite (not just `compileall`) and independently validated the new migration applies and reverses cleanly against a disposable scratch PostgreSQL database, consistent with the standard set in M1.4.

### Known Limitations

- No batch/scheduled runner was added to sweep all `OPEN` recommendations and call `evaluate_recommendation` for each — this EPIC only implements the per-recommendation evaluation primitive, per its own scope ("Evaluate completed ... recommendations", not "build a scheduler"). A batch driver would be a small, natural follow-up but wasn't required by any acceptance criterion here.
- As documented in EPIC-M1.4, the local dev database (`market_agent`) was not touched; only a disposable scratch database was used for migration validation.
- CI (`.github/workflows/test.yml`) still does not run Alembic migrations; this EPIC's tests remain SQLite-fixture-based so they still pass there.

### Unexpected Findings

- **Alembic `version_num` column is `VARCHAR(32)`** (set in `0001_initial`). My first attempt at this migration's revision id, `0006_prediction_outcome_actual_return` (38 characters), overflowed it and failed with `psycopg.errors.StringDataRightTruncation` when stamping the new version — not a data bug, but worth remembering for any future migration: **keep revision ids at or under 32 characters.** Renamed to `0006_outcome_actual_return` (26 characters) and re-validated successfully.
- Confirms the pre-existing broken `0003_market_price_dedupe` migration (documented in EPIC-M1.4) is still present and was again worked around the same way (stamp past it) for this EPIC's validation; not fixed here, still out of scope.

### Architectural Observations

- The bracket-style (target/stop-hit, first-touch) evaluation methodology directly matches the field names already scaffolded in `PredictionOutcome` (`target_hit`, `stop_hit`) from the original M1 foundation, reinforcing the M1.4 observation that this scaffold was designed with this exact evaluation shape in mind.
- M1.6 (Positive Recommendation Performance Report) can now query `PredictionOutcome` directly: `outcome != "UNEVALUABLE"` for the success-rate denominator (per M1.6's own AC), grouped by `outcome`, `prediction.horizon_days`, and `prediction.confidence`/`predicted_probability` buckets, using `prediction_error`/`actual_return` for predicted-vs-actual reporting — no further schema changes should be needed for M1.6.
- M1.7 (Watchlist) also depends on M1.5; `evaluate_recommendation` is stock/recommendation-agnostic (it only needs a `Prediction` row and `MarketPrice` history), so it should work unchanged for watchlist-originated recommendations once M1.7 creates them the same way M1.4's `record_recommendation` does.

### Recommended Follow-up

- A small batch/scheduled runner that calls `evaluate_recommendation` for all `OPEN` predictions whose horizon has elapsed (not implemented here, out of this EPIC's scope).
- Suggestion only; not implemented as part of this EPIC.

### Claude Assessment

I believe this implementation is technically complete against all six acceptance criteria, with real test and migration evidence. Per the corrected contract (2026-08-20), Claude opens this PR and does not merge it — merge remains the user's/reviewer's action.
