# EPIC-M1.67 — Model Regression Detection

Status: READY_FOR_APPROVAL
Execution Status: NOT_READY

## Objective
Detect when a promoted model or scoring change materially degrades real-world recommendation performance.

## Scope
- Monitor production model performance against the approved baseline.
- Detect statistically meaningful degradation.
- Segment regression by horizon, regime, sector, and confidence band where sample sizes permit.
- Trigger a rollback/candidate-disable state.
- Preserve evidence for the regression decision.

## Acceptance Criteria
- Baseline is immutable and versioned.
- Regression thresholds are explicit.
- Small samples do not trigger unsafe conclusions.
- A detected regression cannot silently continue as healthy.

## Dependencies
Previous: M1.66.
Next: M1.68.

## Completion Report
Update this EPIC with final implementation evidence before merge.
