# EPIC-085 — Prediction & Calibration Drift Detection

**Status:** DONE
**Execution Status:** COMPLETED
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
**Previous:** EPIC-062, EPIC-080, EPIC-084.
**Next:** EPIC-082, EPIC-087.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-085

### Branch

autonomous/epic-m1-80, branched cleanly from `main` (the declared dependencies -- EPIC-062, EPIC-080, EPIC-084 -- are already merged).

### Objective

Detect changes in prediction behavior and probability calibration early enough to reduce trust before degraded predictions materially damage recommendation quality.

### Design

`app/prediction_calibration_drift.py` composes rather than duplicates EPIC-062's `detect_model_regression`: that module already answers "has this model's own real-world success rate degraded between two windows," and already segments that answer by horizon and regime (scope item 3). Reusing it directly -- rather than re-deriving the same segmentation -- follows this platform's established "reuse the earlier module's own logic where the question is identical" pattern. This EPIC's own, genuinely new contribution is two signals EPIC-062 does not compute at all: **prediction-distribution drift** (has the raw `predicted_probability` distribution shifted between windows, independent of outcomes) and **calibration drift** (has the *gap* between predicted probability and realized success rate widened -- a model can hold the same success rate while becoming systematically over/under-confident, which a success-rate-only comparison would never catch).

### Versioned, Disjoint Windows And Enforced Sample Thresholds

Reuses EPIC-074's `EvaluationWindow`/`OverlappingEvaluationWindowsError` unchanged; raises on overlapping windows (`test_overlapping_windows_are_rejected`). Below `MIN_SAMPLE_SIZE_FOR_COMPARISON` on either side, the verdict is explicitly `VERDICT_INSUFFICIENT_SAMPLE` with every metric left `None` (AC: "sample-size thresholds are enforced"; `test_insufficient_sample_produces_no_unsafe_conclusion`).

### Real, Hand-Verified Drift Signals

`test_distribution_and_calibration_drift_are_detected` proves both new signals against exact hand-computed numbers (a 0.2 shift in mean predicted probability and a corresponding 0.2 widening of the calibration gap, both against the reused `CALIBRATION_ERROR_MARGIN` = 0.10 threshold). `test_real_regression_is_reflected_as_drift` proves a genuine EPIC-062 regression also surfaces here as drift, since this module's overall verdict is `DRIFT_DETECTED` whenever *any* of the three signals (distribution, calibration, or EPIC-062's own regression verdict) fires.

### Propose, Never Enforce

`trust_reduction_recommended` is exposed for a future consumer (EPIC-087, not yet built) to act on -- this module has no write path to `Prediction`, `ScanCandidate`, or `PredictionTrustScore` itself (`test_detection_never_writes_to_predictions`), matching the Execution Rule: "detection is not proof of failure... it must not silently alter production behavior."

### Files Changed

- `app/prediction_calibration_drift.py` — new: `detect_prediction_calibration_drift`, `get_drift_history`, constants.
- `app/models.py` — new `PredictionCalibrationDrift` model.
- `migrations/versions/0060_calibration_drift.py` — new migration.
- `tests/test_prediction_calibration_drift.py` — new: 7 tests.
- `docs/epics/EPIC-085-prediction-calibration-drift-detection.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_prediction_calibration_drift.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0060_calibration_drift`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0059` through `0060` (verified `prediction_calibration_drifts` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **699 passed, 0 failed**.
- `test_prediction_calibration_drift.py`: **7 passed** — insufficient sample produces no unsafe conclusion (while still linking a real EPIC-062 check); stable calibration and distribution across matching windows is `NO_DRIFT`; a real distribution and calibration shift is detected with exact hand-verified numbers; a genuine EPIC-062-style regression is correctly reflected as drift here too; overlapping windows are rejected; drift history is retained across repeated checks; detection never writes to `Prediction`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Prediction and calibration drift are measurable (`distribution_drift`/`calibration_drift` fields; hand-verified by test).
- [x] Baselines and comparison windows are versioned (EPIC-074's `EvaluationWindow`, unchanged, plus `drift_rule_version`).
- [x] Sample-size thresholds are enforced (`MIN_SAMPLE_SIZE_FOR_COMPARISON` gate; `VERDICT_INSUFFICIENT_SAMPLE`).
- [x] Drift events are auditable (append-only, immutable-by-convention check log, linked to the underlying EPIC-062 regression check).
- [x] Confirmed drift can reduce trust or trigger revalidation (`trust_reduction_recommended` exposed for a future consumer).
- [x] Tests cover false-positive and real-drift cases (`NO_DRIFT` and multiple `DRIFT_DETECTED` scenarios both proven).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and hand-verified exact drift numbers for both new signals this EPIC adds. This EPIC composes EPIC-062's regression check directly for the horizon/regime segmentation dimension rather than re-deriving it, and reuses EPIC-072's own calibration-gap margin rather than inventing a new threshold. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
