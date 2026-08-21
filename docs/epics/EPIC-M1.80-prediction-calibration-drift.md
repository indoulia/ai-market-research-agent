# EPIC-M1.80 — Prediction & Calibration Drift Detection

> **Note (2026-08-21 QA/integration audit):** This file duplicates
> `EPIC-M1.80-prediction-calibration-drift-detection.md`, which is `DONE`
> with a real, verified implementation
> (`app/prediction_calibration_drift.py`). No EPIC numbered ≥110
> references this file or depends on it as unfinished work. Left in
> place, not deleted/renamed — a human should decide whether to formally
> retire it.

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_READY
**Priority:** P0

## Objective
Detect when prediction behavior, probability calibration or recommendation characteristics drift away from historically reliable behavior before trust is materially damaged.

## Scope
- Detect probability-distribution drift.
- Detect confidence-distribution drift.
- Detect calibration drift.
- Detect directional recommendation drift.
- Compare recent and historical windows.
- Segment drift by horizon and regime.
- Feed verified drift into Trust Score and model evaluation.
- Preserve immutable drift events and supporting metrics.

## Acceptance Criteria
- Meaningful drift is detected deterministically.
- False alarms are controlled using sample-size thresholds.
- Calibration degradation reduces trust when supported by evidence.
- Drift events are auditable.
- Drift does not automatically promote or replace a model.

## Dependency Chain
**Previous:** M1.67, M1.77, M1.78, M1.79.
**Next:** M1.81, M1.84.

## Execution Rule
Detection is not proof of failure. Drift creates an investigation/revalidation signal; it must not silently alter production behavior.
