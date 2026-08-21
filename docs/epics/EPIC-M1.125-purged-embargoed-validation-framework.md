# EPIC-M1.125 — Purged & Embargoed Financial Validation Framework

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
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
