# EPIC-M1.102 — Regime Transition & Uncertainty Intelligence

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Detect unstable market-regime transitions and separate inherent market uncertainty from insufficient model knowledge so Trust Score and positive recommendation eligibility respond appropriately.

## Scope
- Detect transitions between market regimes.
- Measure transition confidence and instability.
- Distinguish market uncertainty from data/model uncertainty where feasible.
- Incorporate uncertainty into Trust Score and positive-only gating.
- Preserve regime and uncertainty snapshots with predictions.
- Evaluate transition-period prediction performance separately.

## Acceptance Criteria
- Stable and transitional regimes are distinguishable.
- Transition periods can reduce trust when evidence supports it.
- Uncertainty sources are separately represented.
- Historical transition behavior is measurable.
- No automatic recommendation downgrade to a negative/cautious user-facing state; low-trust candidates are suppressed instead.

## Dependencies
Previous: M1.79, M1.101.
Next: M1.103.
