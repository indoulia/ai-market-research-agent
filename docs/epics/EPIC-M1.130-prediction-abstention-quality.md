# EPIC-M1.130 — Prediction Abstention Quality & Opportunity Suppression Learning

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Measure whether MRA's positive-only suppression decisions are themselves correct, preventing the system from becoming either recklessly permissive or excessively conservative.

## Scope
- Preserve qualified-but-suppressed candidates and reasons.
- Define abstention outcomes for suppressed opportunities.
- Measure missed-opportunity rate, false-positive avoidance and suppression utility.
- Segment abstention quality by horizon, regime, sector, stock/setup and trust level.
- Learn thresholds that balance opportunity capture with recommendation quality.
- Feed validated abstention evidence into ranking and Trust policy.
- Keep user-facing output positive-only.

## Acceptance Criteria
- Every suppression has a reason and policy version.
- Suppressed candidates can be evaluated retrospectively without becoming user recommendations.
- MRA can quantify both harmful publication and harmful suppression.
- Threshold changes require controlled validation.
- Historical suppression decisions remain immutable.

## Dependencies
M1.87, M1.99, M1.100, M1.110.

## Non-Goal
Do not introduce negative/cautious recommendations to the user-facing feed.
