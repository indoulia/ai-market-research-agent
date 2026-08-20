# EPIC-M1.38 — Objective Recommendation Outcome Measurement

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Determine recommendation success or failure using predefined, immutable outcome rules rather than subjective interpretation.

## Scope
- Define success/failure/neutral/insufficient-data outcomes.
- Calculate realized return at the selected horizon.
- Apply target and loss thresholds consistently.
- Handle price gaps and missing observations explicitly.
- Freeze final outcome after sufficient evidence exists.
- Preserve outcome calculation version.

## Acceptance Criteria
- [ ] Every completed recommendation receives one deterministic outcome state.
- [ ] Outcome rules are versioned.
- [ ] Success/failure cannot be changed without a new versioned evaluation.
- [ ] Missing data never becomes an assumed success/failure.
- [ ] Outcome calculation is reproducible from stored observations.
- [ ] Tests cover boundary conditions.

## Dependencies
**Previous:** M1.36, M1.37
**Next:** M1.39

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.38

### Branch

autonomous/epic-m1-38, branched cleanly from `main` (both declared dependencies -- M1.36 and M1.37 -- are already merged).

### Objective

Determine recommendation success/failure/neutral/insufficient-data using predefined, immutable, versioned rules, without touching M1.5's foundational outcome computation.

### Design Decisions

- **Deliberately does not modify `app/outcomes.py` (M1.5).** That module is the foundational, heavily-tested source of the objective per-recommendation result (target/stop-hit detection, realized return at the selected horizon, invalid-data handling) that a large fraction of this platform's already-merged EPICs (M1.15, M1.21, M1.23, and every analysis EPIC downstream) depend on and are tested against. Modifying its core classification logic now would be genuinely risky for no real benefit.
- **What M1.5's `PredictionOutcome` actually lacks -- and what this EPIC adds** -- is a traceable classification *version* (it has none at all) and an explicit `NEUTRAL` category. M1.5's own fallback path (no threshold hit) classifies purely by the sign of `actual_return`, even when that return is negligibly close to zero; the scope explicitly names `NEUTRAL` as a fourth first-class outcome alongside success/failure/insufficient-data, which nothing in this repo currently produces.
- **New table `outcome_measurements`** (migration `0027`, chains off M1.37's `0026`): one immutable row per `PredictionOutcome` (unique `prediction_outcome_id`), never updated after creation (`before_update` guard). Every other classification M1.5 already determined (target hit → `SUCCESS`, stop hit → `FAILURE`, invalid data → M1.38's `INSUFFICIENT_DATA`, explicitly renamed from M1.5's `UNEVALUABLE` to match this EPIC's own named vocabulary) passes through completely unchanged; only the narrow "no threshold hit, return near zero" case is reclassified.
- **`NEUTRAL_RETURN_BAND = Decimal("0.005")`** (fixed, documented, versioned via `MEASUREMENT_RULE_VERSION = "OMS-001"`): a realized return within ±0.5% of zero, with neither target nor stop hit, is `NEUTRAL` rather than an arbitrary sign-based `SUCCESS`/`FAILURE` call. The boundary is inclusive (`abs(actual_return) <= NEUTRAL_RETURN_BAND` → `NEUTRAL`), proven directly by a boundary test.
- **"Missing data never becomes an assumed success/failure" (AC)** holds because `UNEVALUABLE` maps to `INSUFFICIENT_DATA` unconditionally, before any return-based classification is even considered, and `realized_return` is explicitly `None` for that case rather than echoing M1.5's placeholder `actual_return=0`.
- **"Success/failure cannot be changed without a new versioned evaluation" (AC)**: `measure_outcome` is idempotent by `prediction_outcome_id` uniqueness (re-measuring returns the original row) and the row itself is immutable; a future rule change would ship under a new `MEASUREMENT_RULE_VERSION` and produce a distinct new row, never mutate an existing one.
- **"Freeze final outcome after sufficient evidence exists" (scope)** holds structurally: `measure_outcome` only ever accepts an already-persisted `PredictionOutcome`, which itself only exists once M1.5 has completed evaluating the full horizon window -- there is no code path to measure an in-progress recommendation.

### Files Changed

- `app/outcome_measurement.py` — new: `measure_outcome`, `get_outcome_measurement`, outcome/version constants, `OutcomeMeasurementImmutableError`.
- `app/models.py` — new `OutcomeMeasurement` model.
- `migrations/versions/0027_outcome_measurements.py` — new migration.
- `tests/test_outcome_measurement.py` — new: 9 tests.
- `docs/epics/EPIC-M1.38-objective-outcome-measurement.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_outcome_measurement.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0027_outcome_measurements`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0026` through `0027` (verified `outcome_measurements` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results (edge-case and reproducibility evidence)

- `pytest -q`: **329 passed, 0 failed** (320 pre-existing from `main` + 9 new).
- `pytest -v tests/test_outcome_measurement.py`: **9 passed** — an `UNEVALUABLE` M1.5 outcome measures as `INSUFFICIENT_DATA` with `realized_return=None`; a target-hit outcome measures `SUCCESS`; a stop-hit outcome measures `FAILURE`; a zero-return, no-threshold-hit outcome measures `NEUTRAL`; a return exactly at the `±0.5%` boundary measures `NEUTRAL` (inclusive edge); returns just beyond the boundary in each direction measure `SUCCESS`/`FAILURE` correctly; re-measuring the same outcome twice is idempotent (same row); a direct mutation attempt after creation raises `OutcomeMeasurementImmutableError`; and a prior measurement can be retrieved by its outcome id.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Every completed recommendation receives one deterministic outcome state (`_classify` is a pure function of the stored `PredictionOutcome`).
- [x] Outcome rules are versioned (`MEASUREMENT_RULE_VERSION`).
- [x] Success/failure cannot be changed without a new versioned evaluation (immutability guard + idempotent re-measurement).
- [x] Missing data never becomes an assumed success/failure (`INSUFFICIENT_DATA`, unconditional, `realized_return=None`).
- [x] Outcome calculation is reproducible from stored observations (pure function over already-stored `PredictionOutcome` fields, no live recomputation).
- [x] Tests cover boundary conditions (the exact `±0.5%` neutral-band edge, in both directions).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and explicit boundary tests at the neutral-band edge. Deliberately not touching M1.5's own classification logic -- only adding a versioned, additive layer on top -- is the central design decision, documented above for reviewer scrutiny. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->