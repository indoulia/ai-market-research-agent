# EPIC-M1.100 — Experiment Multiplicity & Holdout Protection

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Prevent MRA's self-learning system from selecting apparently superior models or strategies merely because many experiments were tried against the same historical evidence.

## Scope
- Maintain an immutable experiment registry.
- Record all candidate experiments and evaluation datasets.
- Protect untouched final holdout periods.
- Track repeated trials against shared data.
- Apply multiple-testing awareness to candidate selection.
- Prevent repeated tuning against the final holdout.
- Require independent confirmation before promotion.
- Preserve experiment lineage and promotion evidence.

## Acceptance Criteria
- Every experiment is registered before evaluation.
- Final holdout data cannot be used for iterative tuning.
- Candidate selection accounts for repeated experimentation.
- Promotion requires independent evidence.
- Experiment history is immutable and auditable.

## Dependencies
Previous: M1.25, M1.68, M1.88, M1.97, M1.99.
Next: M1.101.

## Completion Report

**Status:** DONE — merged to main via PR #148 (`a0b55c6`).

**Implementation:**
- `app/experiment_integrity_guard.py`: a new, versioned (`EXPERIMENT_INTEGRITY_VERSION = "EIG-001"`) module that adds exactly the three capabilities M1.68's already-merged experiment registry (`Experiment`/`ExperimentArm`/`ExperimentResult`) never had, without reimplementing the registry itself:
- **Protect untouched final holdout periods / prevent repeated tuning against the final holdout:** `register_holdout_window` immutably registers a labeled window (redefining an existing label's bounds raises `HoldoutRedefinitionError`); `record_holdout_usage` enforces, via a DB unique constraint on `holdout_label`, that a given holdout can be consumed by at most one `ExperimentArm`, ever -- a second attempt raises `HoldoutAlreadyConsumedError`.
- **Track repeated trials against shared data / apply multiple-testing awareness to candidate selection:** `count_trials_for_model_version` counts every registered `ExperimentArm` for a model version; `evaluate_multiplicity_adjusted_significance` scales `WEAKNESS_MARGIN` by that trial count (a fixed, documented Bonferroni-style correction) before a candidate's observed success-rate delta can be called `SIGNIFICANT_AFTER_CORRECTION` -- the same delta that looks significant after one trial stops looking significant after five.
- **Require independent confirmation before promotion:** `require_independent_confirmation` reuses M1.25's own `VERDICT_VALIDATED`/`VERDICT_REGRESSED`/`VERDICT_INSUFFICIENT_EVIDENCE` vocabulary and `REGRESSION_MARGIN`, applied independently to TWO disjoint windows against the same baseline (never reusing evidence) -- `both_validated` is only `True` when both windows independently agree, not just the one window that happened to look good. Raises `OverlappingEvaluationWindowsError` if any pair of the three windows overlaps.
- **Preserve experiment lineage and promotion evidence:** every decision (`MultiplicityGuardDecision`, `IndependentConfirmationDecision`, `HoldoutUsageRecord`) is a new, append-only, immutable table (migration `0075_experiment_integrity_guard.py`), idempotent by its natural key.
- No write path to `Experiment`, `ExperimentArm`, `ModelPromotion`, or any other production/promotion table -- this remains a propose-only pre-check; actual promotion authority stays exclusively with M1.31/M1.44.

**Tests:** `tests/test_experiment_integrity_guard.py` (11 tests) — holdout registration idempotency/redefinition rejection, one-time holdout consumption (including the unknown-holdout case), trial counting, multiplicity-adjusted significance flipping from significant to not-significant as trial count grows, idempotency, independent-confirmation validated/insufficient/overlapping-window cases.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_experiment_integrity_guard.py -q` → `11 passed`
- `python -m pytest -q` (full suite) → `926 passed`
- `python -m alembic heads` → single head `0075_experiment_integrity (head)`, chain resolves cleanly
