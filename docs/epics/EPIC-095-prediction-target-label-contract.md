# EPIC-095 — Prediction Target & Label Contract

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Define immutable, point-in-time-safe prediction targets and outcome labels so MRA learns from a stable definition of success.

## Scope
- Define labels for 1/2/3/5/7 trading-day horizons.
- Freeze reference price, target, stop-loss, horizon and benchmark at prediction creation.
- Define target-hit, stop-loss-hit, horizon-expiry and invalidation outcomes.
- Handle same-day target/SL ambiguity deterministically.
- Preserve label methodology/version with every prediction.
- Ensure labels cannot use future information beyond the defined outcome window.
- Add reproducible label-generation and boundary tests.

## Acceptance Criteria
- Every prediction has an immutable label contract.
- Outcome calculation is deterministic.
- Historical labels cannot change when methodology versions change.
- Future data leakage is prevented.
- Labels support model training, calibration and trust measurement consistently.

## Dependencies
Previous: EPIC-070, EPIC-042, EPIC-079.
Next: EPIC-096.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-095

### Branch

autonomous/epic-m1-95, branched cleanly from `main` (all three declared dependencies -- EPIC-070, EPIC-042, EPIC-079 -- are already merged).

### Objective

Define immutable, point-in-time-safe prediction targets and outcome labels so this platform learns from a stable definition of success.

### Most Of This Contract Already Existed -- Verified, Not Rebuilt

Before writing any code, I audited what EPIC-005/EPIC-010/EPIC-079 already guarantee, since re-implementing an already-correct guarantee would violate this platform's own "compose, don't duplicate" discipline:

- **"Freeze reference price, target, stop-loss and horizon at prediction creation"** -- already true. `app/recommendations.py`'s `before_update` guard on `Prediction` already includes `entry_price`, `horizon_days`, `target_return`, `stop_return`, `as_of_timestamp` in its `IMMUTABLE_FIELDS`; `test_original_recommendation_is_unchanged_by_evaluation` already proved it. No new code needed here.
- **"Handle same-day target/SL ambiguity deterministically"** -- already true. `app/outcomes.py`'s `_find_exit` checks stop-loss before the profit target on the same trading day, by explicit, documented convention. `test_stop_checked_before_target_on_same_day` already proved it; this EPIC adds `test_same_day_ambiguity_is_deterministic_stop_first` at the new label-category layer for the same guarantee.
- **"Ensure labels cannot use future information beyond the defined outcome window"** -- already true. `evaluate_recommendation` only ever queries `MarketPrice.timestamp > prediction.as_of_timestamp` and slices exactly `window = rows[:horizon_days]`. `test_leakage_boundary_price_beyond_horizon_never_used` (new) proves a huge price spike placed one day beyond the horizon is never allowed to affect the outcome.
- **Historical outcomes were already immutable** -- `PredictionOutcome` already had a `before_update` guard (`OutcomeImmutableError`) over every substantive field.

### The Real, Concrete Gaps This EPIC Closes

1. **"Preserve label methodology/version with every prediction" had no field to preserve it in.** `PredictionOutcome` recorded *what* happened (`target_hit`, `stop_hit`, `outcome`) but never *which version of the labeling methodology* decided it. Added `label_methodology_version` (nullable, additive migration `0068_label_version`) plus `LABEL_METHODOLOGY_VERSION = "LBL-001"` in `app/outcomes.py`, now populated on every newly-created outcome (both the normal and `UNEVALUABLE` paths) and added to the existing `IMMUTABLE_FIELDS` guard. Pre-EPIC rows have `label_methodology_version IS NULL`, honestly meaning "not recorded at the time" -- never backfilled with a guess. `test_a_methodology_version_bump_never_rewrites_history` proves directly that bumping the module's version constant between two evaluations never touches the first outcome's already-recorded version.
2. **No canonical label-category vocabulary existed.** Consumers had to interpret raw `target_hit`/`stop_hit`/`outcome` booleans and strings themselves, inconsistently, to answer "was this a target hit, a stop-loss hit, a horizon expiry, or invalidated?" (scope: "define target-hit, stop-loss-hit, horizon-expiry and invalidation outcomes"; AC: "labels support model training, calibration and trust measurement consistently"). Added `classify_label_category(outcome) -> str` -- a pure function over fields `evaluate_recommendation` already computed, never a second opinion on what happened -- returning one of `TARGET_HIT`, `STOP_LOSS_HIT`, `HORIZON_EXPIRY`, or `INVALIDATED`. The existing `outcome == "UNEVALUABLE"` case (bad OHLC data made the true exit undeterminable) maps honestly to `INVALIDATED` -- the one existing case where a label genuinely cannot be trusted for training.

### The 1/2/3/5/7 Horizon Vocabulary

Scope asks to "define labels for 1/2/3/5/7 trading-day horizons." EPIC-079's `short_horizon_probability.SUPPORTED_HORIZON_DAYS = (1, 2, 3, 5, 7)` is already exactly this named vocabulary, already documented as deliberately including day 2 even though `app.recommendations.VALID_HORIZON_DAYS = (1, 3, 5, 7)` (EPIC-010's horizon-selection logic) never actually produces a day-2 prediction today. This EPIC does not touch EPIC-010's selection logic (not a declared dependency, and already merged/tested business logic this session has consistently left alone) -- `test_label_contract_horizon_vocabulary_is_a_documented_superset` proves the two constants' documented relationship holds (`VALID_HORIZON_DAYS` is a subset of `SUPPORTED_HORIZON_DAYS`) rather than silently re-deciding it.

### "Benchmark" Reference

Scope also asks to freeze a "benchmark" at prediction creation. This codebase has no real benchmark instrument (no NIFTY or index feed is ingested anywhere -- EPIC-086/EPIC-089 already established, honestly, that a real benchmark comparison reports `BENCHMARK_DATA_UNAVAILABLE` rather than fabricating one). The only real "benchmark" a `Prediction` is actually judged against is its own frozen `target_return`/`stop_return` -- already immutable via EPIC-010's own guard. No new benchmark field was invented here; fabricating an index reference this platform has no real data for would violate the same honesty discipline every prior EPIC in this session has held.

### Files Changed

- `app/models.py` — `PredictionOutcome` gains a nullable `label_methodology_version: Mapped[str | None]` column (additive).
- `app/outcomes.py` — new `LABEL_METHODOLOGY_VERSION`, `LABEL_TARGET_HIT`/`LABEL_STOP_LOSS_HIT`/`LABEL_HORIZON_EXPIRY`/`LABEL_INVALIDATED`, `classify_label_category`; `label_methodology_version` added to `IMMUTABLE_FIELDS` and populated on both outcome-creation paths.
- `migrations/versions/0068_label_methodology_version.py` — new, additive, nullable column; `downgrade()` drops it cleanly.
- `tests/test_prediction_label_contract.py` — new: 11 tests.
- `docs/epics/EPIC-095-prediction-target-label-contract.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_prediction_label_contract.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0068_label_version`)
- Real PostgreSQL (`market_agent` DB): `alembic upgrade head` (added the column), verified via `sqlalchemy.inspect` that `label_methodology_version VARCHAR(32)` exists and is nullable, `alembic downgrade -1` (verified the column was dropped), `alembic upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **836 passed, 0 failed** (825 pre-existing + 11 new).
- `test_prediction_label_contract.py`: **11 passed** — a new outcome records the methodology version; that version is immutable; a version bump between two evaluations never rewrites the first outcome's recorded version; `classify_label_category` correctly maps target-hit, stop-loss-hit, both signs of horizon-expiry, and invalidated (`UNEVALUABLE`) outcomes; classification is deterministic and reproducible across repeated calls; same-day target/stop ambiguity remains stop-first at the label-category layer; a price spike one day beyond the horizon never leaks into the outcome; `VALID_HORIZON_DAYS` is confirmed a documented subset of `SUPPORTED_HORIZON_DAYS`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Real-Postgres migration round-trip: column added, verified present and nullable, dropped on downgrade, cleanly re-applied on upgrade.

### Acceptance Criteria

- [x] Every prediction has an immutable label contract (`Prediction`'s own fields via EPIC-010's existing guard; `PredictionOutcome`'s fields, now including `label_methodology_version`, via EPIC-005's existing guard, extended here).
- [x] Outcome calculation is deterministic (`test_classification_is_deterministic_and_reproducible`, `test_same_day_ambiguity_is_deterministic_stop_first`).
- [x] Historical labels cannot change when methodology versions change (`test_a_methodology_version_bump_never_rewrites_history`).
- [x] Future data leakage is prevented (`test_leakage_boundary_price_beyond_horizon_never_used`, composing EPIC-005's existing structural guarantee).
- [x] Labels support model training, calibration and trust measurement consistently (`classify_label_category`'s single canonical four-category vocabulary).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence. Most of this EPIC's scope was already correctly implemented by EPIC-005/EPIC-010/EPIC-079; the two genuine, concrete gaps -- a missing methodology-version field and a missing canonical label-category vocabulary -- are now closed additively, without touching or duplicating any already-merged, already-tested computation. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
