# EPIC-M1.80 — Prediction & Calibration Drift Detection

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Approved By:** User
**Priority:** P0

## Objective
Detect changes in prediction behavior and probability calibration early enough to reduce trust before degraded predictions materially damage recommendation quality.

## Scope
- Detect prediction-distribution drift.
- Detect calibration drift.
- Detect changes in outcome rates by horizon and regime.
- Compare recent windows with validated baseline windows.
- Persist drift events and evidence.
- Feed confirmed drift into Trust and learning controls.
- Avoid triggering on statistically insignificant noise.

## Acceptance Criteria
- Prediction and calibration drift are measurable.
- Baselines and comparison windows are versioned.
- Sample-size thresholds are enforced.
- Drift events are auditable.
- Confirmed drift can reduce trust or trigger revalidation.
- Tests cover false-positive and real-drift cases.

## Dependency Chain
**Previous:** M1.67, M1.77, M1.79.
**Next:** M1.81, M1.84.
