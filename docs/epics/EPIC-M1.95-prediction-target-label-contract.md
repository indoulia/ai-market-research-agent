# EPIC-M1.95 — Prediction Target & Label Contract

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
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
Previous: M1.21, M1.47, M1.75.
Next: M1.96.
