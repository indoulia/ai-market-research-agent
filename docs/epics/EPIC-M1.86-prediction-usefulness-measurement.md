# EPIC-M1.86 — Prediction Usefulness Measurement

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Approved By:** User
**Priority:** P1

## Objective
Measure whether positive recommendations are genuinely useful to an investor, not merely directionally correct.

## Scope
- Measure target-hit rate, stop-loss rate, realized return and time-to-target.
- Measure maximum favorable and adverse excursion.
- Measure benchmark-relative performance and alpha.
- Distinguish directional correctness from investment usefulness.
- Measure risk-adjusted usefulness by horizon.
- Feed usefulness metrics into Trust Score and learning.
- Preserve historical measurements immutably.

## Acceptance Criteria
- Every closed recommendation receives usefulness metrics where data permits.
- Benchmark-relative performance is available.
- Directional accuracy and investment usefulness are separately reported.
- Metrics are segmented by horizon and regime.
- Insufficient data is explicit.
- Trust can only improve from measured usefulness evidence.

## Dependencies
Previous: M1.47, M1.75, M1.77, M1.82.
Next: M1.87.
