# EPIC-M1.49 — Confidence Calibration

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1  
**Dependency:** M1.16, M1.38

## Objective
Make prediction confidence a calibrated probability grounded in observed historical outcomes rather than an unverified model score.

## Scope
- Compare predicted confidence/probability with realized success rates.
- Calibrate by horizon and relevant probability bands.
- Preserve calibration version.
- Produce calibration metrics and reliability diagnostics.
- Keep raw model probability separate from calibrated confidence.

## Acceptance Criteria
- Raw and calibrated confidence are stored separately.
- Calibration uses only eligible historical outcomes.
- Calibration avoids future-data leakage.
- Sample insufficiency is explicitly reported.
- Calibration metrics are reproducible.
- Tests cover calibration, empty data, and insufficient samples.

## Dependency Chain
M1.16/M1.38 → M1.49 → M1.50

## Completion Report
<!-- Claude: populate only after implementation. Preserve review history. -->
