# EPIC-M1.89 — Prediction Quality Monitoring & Trust Dashboard

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Make the evolution of prediction quality, trust and learning visible over time so users can understand whether MRA is actually becoming more reliable.

## Scope
- Show trust score history.
- Show accuracy, calibration and usefulness trends.
- Show target/SL/horizon performance.
- Show performance by horizon and regime.
- Show positive recommendation count versus successful recommendation count.
- Show suppressed-candidate statistics without presenting negative recommendations as user recommendations.
- Show model versions, promotions, regressions and learning events.
- Show data/evidence quality trends.
- Provide drill-down from aggregate trust to individual prediction history.

## Acceptance Criteria
- Users can see whether trust is increasing or decreasing over time.
- Historical prediction states are reconstructable.
- Model changes and their measured impact are visible.
- Metrics distinguish current performance from historical performance.
- Dashboard never hides negative evidence needed to understand trust.
- User-facing recommendation feed remains positive-only.

## Dependencies
Previous: M1.77, M1.78, M1.80, M1.82, M1.84, M1.88.
Next: M1.117 validation gate.
