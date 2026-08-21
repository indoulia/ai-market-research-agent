# EPIC-M1.125 — Purged & Embargoed Financial Validation Framework

**Status:** DONE
**Execution Status:** COMPLETE
**Priority:** P0

## Objective
Make time-overlapping financial labels and dependent observations safe for model evaluation by enforcing purged and embargoed validation policies.

## Scope
- Represent each prediction's information timestamp and outcome interval.
- Detect overlap between training and validation label windows.
- Purge overlapping observations from training folds.
- Apply configurable embargo around validation boundaries.
- Support walk-forward and expanding-window validation.
- Keep final holdout untouched by iterative model development.
- Produce validation-fold lineage and exclusion reasons.
- Add adversarial tests for overlapping horizons and temporal leakage.
- Integrate with M1.97 and M1.100 gates.

## Acceptance Criteria
- Overlapping label windows cannot contaminate validation folds.
- Embargo policy is explicit, configurable and versioned.
- Walk-forward evaluation is reproducible.
- Training/validation membership can be reconstructed for every experiment.
- Validation fails closed when temporal metadata is missing or ambiguous.
- No model can be promoted without passing the required validation policy.

## Dependencies
M1.95, M1.97, M1.100, M1.115.

## Architectural Rule
**Temporal validation policy is a mandatory platform gate for financial model evaluation, not an optional backtest configuration.**

## Implementation

**Status:** DONE — merged to main via PR #230 (`8db885e`).

`app/purged_embargo_validation.py` adds purge/embargo semantics on top of M1.25's `EvaluationWindow`:

- `get_label_windows` represents each prediction's `[as_of_timestamp, outcome resolution timestamp]` label window (`None` outcome timestamp when unresolved).
- `generate_walk_forward_folds` is a pure, deterministic generator of rolling or expanding-window fold plans.
- `compute_purged_training_set` purges a training-window prediction if its label window overlaps the embargoed validation window, its outcome is unresolved, it falls inside any M1.100 `HoldoutWindowRegistry` window, or it fails M1.97's `TRAINING`-workflow bias guard; it raises `HoldoutContaminationError` if the validation window itself overlaps an unsanctioned holdout, and `AmbiguousValidationWindowError` if either window lacks explicit bounds.
- `record_validation_fold` persists immutable fold lineage (`validation_folds`: eligible/excluded prediction ids, exclusion reason counts) keyed by `(model_version, fold_index, computed_at)`.
- `evaluate_temporal_validation_policy` is the mandatory PASS/FAIL gate (`temporal_validation_policy_decisions`) a promotion pipeline must consult — same propose-only posture as M1.100, not wired into M1.31/M1.44 directly.

Migration `0097_purged_embargo_validation` adds both tables. 22 new tests in `tests/test_purged_embargo_validation.py`; full suite (1193 tests) green.
