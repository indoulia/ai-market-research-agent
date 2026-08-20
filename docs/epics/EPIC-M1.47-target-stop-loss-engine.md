# EPIC-M1.47 — Recommendation Target & Stop-Loss Engine

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1  
**Dependency:** M1.14

## Objective
Produce explicit, internally consistent target price, stop-loss, upside percentage, downside percentage, horizon, and reward/risk values for every published recommendation.

## Scope
- Calculate target and stop-loss using horizon-appropriate evidence.
- Derive upside/downside percentages from the stored reference price.
- Validate reward/risk and numerical consistency before publication.
- Record target/SL methodology and version.
- Freeze published values; later changes become a new recommendation version.

## Acceptance Criteria
- Every published recommendation has target, SL, horizon, upside %, downside %, and reward/risk where applicable.
- Derived percentages reconcile exactly with stored prices.
- Invalid or contradictory values prevent publication.
- Target/SL calculation is deterministic for the same inputs and version.
- Historical recommendations retain their original values.
- Tests cover normal, boundary, and invalid cases.

## Dependency Chain
M1.14 → M1.47 → M1.48/M1.50+

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.47

### Branch

autonomous/epic-m1-47, branched cleanly from `main` (the declared dependency -- M1.14 -- is already merged).

### Objective

Produce an explicit, internally consistent target price, stop-loss price, upside percentage, downside percentage, horizon, and reward/risk ratio for every published recommendation, frozen under a versioned methodology -- without modifying M1.4/M1.13's existing `Prediction` fields at all.

### Design

`RecommendationPublication` is a new, additive table: one immutable row per `(prediction_id, methodology_version)`. `publish_recommendation` derives `target_price = entry_price * (1 + target_return)` and `stop_loss_price = entry_price * (1 + stop_return)` directly from `Prediction`'s own frozen fields, computes `upside_percentage`/`downside_percentage` from the same returns, and `reward_risk_ratio = upside_percentage / downside_percentage` where the denominator is non-zero ("where applicable" -- `None` otherwise).

### Validation Before Publication

Three checks, any one of which rejects (AC: "invalid or contradictory values prevent publication"): `entry_price <= 0` → `REASON_NON_POSITIVE_ENTRY_PRICE`; `target_return <= 0` → `REASON_TARGET_NOT_ABOVE_ENTRY`; `stop_return >= 0` → `REASON_STOP_NOT_BELOW_ENTRY`. A rejected attempt is still recorded (`published=False`, `rejection_reason` set) rather than silently producing nothing -- consistent with this platform's established "always an audit trail, never a silent drop" convention.

### Reconciliation Guarantee

Because `target_price`/`stop_loss_price` are derived arithmetically from the exact same `entry_price`/`target_return`/`stop_return` used to compute `upside_percentage`/`downside_percentage`, the two representations reconcile exactly by construction (AC: "derived percentages reconcile exactly with stored prices") -- `publish_recommendation` asserts this invariant directly (once the input is known valid) rather than merely assuming it, and `test_derived_percentages_reconcile_exactly_with_stored_prices` proves it holds by independently recomputing the percentages from the stored prices and comparing.

### Determinism & Historical Immutability

`publish_recommendation` is idempotent by `(prediction_id, methodology_version)` uniqueness -- the same prediction and methodology version always return the identical row, never re-derived (AC: "target/SL calculation is deterministic for the same inputs and version"). `RecommendationPublication` carries a `before_update` immutability guard (`RecommendationPublicationImmutableError`) so a published row can never be edited in place. "Later changes become a new recommendation version" (scope) means a *different* `methodology_version` produces an entirely separate row for the same prediction, proven directly by `test_a_new_methodology_version_produces_a_separate_row_not_a_mutation` -- the same versioned-dataset pattern M1.39 already established. `Prediction` itself is never written to by this module (proven by `test_publication_never_mutates_the_original_prediction`).

### Files Changed

- `app/target_stop_loss.py` — new: `publish_recommendation`, `get_publication`, `TARGET_STOP_METHODOLOGY_VERSION`, rejection-reason constants, `RecommendationPublicationImmutableError`.
- `app/models.py` — new `RecommendationPublication` model.
- `migrations/versions/0032_recommendation_publications.py` — new migration.
- `tests/test_target_stop_loss.py` — new: 10 tests.
- `docs/epics/EPIC-M1.47-target-stop-loss-engine.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_target_stop_loss.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0032_recommendation_publications`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0031` through `0032` (verified `recommendation_publications` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **414 passed, 0 failed** (404 pre-existing from `main` + 10 new).
- `pytest -q tests/test_target_stop_loss.py -v`: **10 passed** — a normal case produces a consistent target/stop/reward-risk; derived percentages reconcile exactly with the stored prices via independent recomputation; a near-boundary nonzero downside still yields a real reward/risk ratio; a non-positive entry price, a non-positive target return, and a non-negative stop return are each rejected with the correct reason; publication is deterministic/idempotent on rerun; a new methodology version produces a genuinely separate row rather than mutating the original; a publication row is immutable after creation; the original `Prediction` is never mutated by publishing.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Every published recommendation has target, SL, horizon, upside %, downside %, and reward/risk where applicable (all populated on every `published=True` row).
- [x] Derived percentages reconcile exactly with stored prices (asserted directly in the function; proven independently by test).
- [x] Invalid or contradictory values prevent publication (`published=False` with an explicit reason for all three validation failures).
- [x] Target/SL calculation is deterministic for the same inputs and version (idempotent by `(prediction_id, methodology_version)`).
- [x] Historical recommendations retain their original values (`Prediction` never written to; `RecommendationPublication` itself immutable after creation).
- [x] Tests cover normal, boundary, and invalid cases (10 tests spanning all three categories).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct, independently-recomputed proof of price/percentage reconciliation. This EPIC is purely additive on top of M1.4/M1.13's existing, immutable `Prediction` fields -- it never modifies the underlying recommendation contract, only derives and freezes a richer, validated presentation of it. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
