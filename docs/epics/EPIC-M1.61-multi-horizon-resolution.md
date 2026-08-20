# EPIC-M1.61 — Multi-Horizon Recommendation Resolution

Status: APPROVED
Execution Status: READY_FOR_EXECUTION

## Objective
Represent short-, medium-, and long-term views independently and clearly resolve conflicting horizon outcomes.

## Scope
- Preserve horizon-specific scores, confidence, target, and SL.
- Detect conflicts between horizons.
- Define deterministic presentation priority based on user preference.
- Never hide a material conflicting view.

## Acceptance Criteria
- Default user horizon remains short term (1–7 days).
- Other horizons are opt-in/configurable.
- Conflicts are explicitly surfaced.
- Historical horizon decisions remain immutable.

## Dependencies
Previous: M1.60.
Next: M1.62.

## Completion Report
Update this EPIC with final implementation evidence before merge.
