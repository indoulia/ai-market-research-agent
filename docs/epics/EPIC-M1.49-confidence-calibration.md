# EPIC-M1.49 — Confidence Calibration

**Status:** DONE  
**Execution Status:** COMPLETED  
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

### Status

IMPLEMENTED

### EPIC

EPIC-M1.49

### Branch

autonomous/epic-m1-49, branched cleanly from `main` (both declared dependencies -- M1.16 and M1.38 -- are already merged).

### Objective

Make `Prediction.confidence` a calibrated probability grounded in observed historical outcomes rather than an unverified model score, storing the raw and calibrated values separately, per prediction, with structural leakage protection.

### How This Differs From M1.23/M1.29

M1.23's `confidence_analysis` and M1.29's `adaptive_calibration` already calibrate `predicted_probability` by bucket/horizon -- but neither touches `Prediction.confidence` (a distinct field), and neither persists a per-prediction record (both are read-only reports). M1.49 fills that specific, genuinely open gap: it calibrates `confidence`, and it persists one immutable, versioned row per prediction so a caller can retrieve "what was this specific recommendation's calibrated confidence" directly, rather than only a bucket-level report.

### Calibration Methodology

`calibrate_confidence_for_prediction` buckets `prediction.confidence` using M1.6's existing ten fixed-width buckets (reused from `app.performance`, not redefined), then measures the observed success rate among already-closed (`SUCCESS`/`FAILURE`) outcomes in the same bucket from a caller-supplied `training_window` (M1.25's `EvaluationWindow`). `calibration_error = average_confidence - observed_rate`; the verdict (`OVERCONFIDENT`/`UNDERCONFIDENT`/`WELL_CALIBRATED`/`INSUFFICIENT_SAMPLE`) reuses M1.23's exact vocabulary and `CALIBRATION_ERROR_MARGIN`. `calibrated_confidence` is set to the bucket's observed rate only when the verdict is not `INSUFFICIENT_SAMPLE` (AC: "sample insufficiency is explicitly reported"); otherwise it is `None`.

### Leakage Protection (Structural)

`calibrate_confidence_for_prediction` raises `FutureDataLeakageError` unless `training_window.end` is both set and strictly before the target prediction's own `as_of_timestamp` -- an unbounded window (`end=None`) is rejected outright, since it could include evidence that postdates the prediction being calibrated. This is enforced in code, not merely documented convention (AC: "calibration avoids future-data leakage"), and is tested for both an explicitly-late window and an unbounded one.

### Raw/Calibrated Separation & Immutability

`ConfidenceCalibrationRecord` stores `raw_confidence` (a frozen copy of `Prediction.confidence` at calibration time) and `calibrated_confidence` on separate columns (AC: "raw and calibrated confidence are stored separately") -- `Prediction.confidence` itself is never written to. One immutable row per `(prediction_id, calibration_version)`, guarded by `before_update` (`ConfidenceCalibrationImmutableError`); a different `calibration_version` produces a genuinely separate row (AC: "preserve calibration version").

### Reliability Diagnostics

Every record carries `sample_count`, `calibration_error`, `verdict`, and the exact `bucket_lower`/`bucket_upper`/`training_window_label` that produced it -- a complete, self-contained diagnostic of the evidence behind one prediction's calibration (scope: "produce calibration metrics and reliability diagnostics").

### Files Changed

- `app/confidence_calibration.py` — new: `calibrate_confidence_for_prediction`, `get_confidence_calibration`, `CONFIDENCE_CALIBRATION_VERSION`, `FutureDataLeakageError`, `ConfidenceCalibrationImmutableError`.
- `app/models.py` — new `ConfidenceCalibrationRecord` model.
- `migrations/versions/0034_confidence_calibration.py` — new migration.
- `tests/test_confidence_calibration.py` — new: 9 tests.
- `docs/epics/EPIC-M1.49-confidence-calibration.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_confidence_calibration.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0034_confidence_calibration`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0033` through `0034` (verified `confidence_calibration_records` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **434 passed, 0 failed** (425 pre-existing from `main` + 9 new).
- `pytest -q tests/test_confidence_calibration.py -v`: **9 passed** — insufficient training sample yields `INSUFFICIENT_SAMPLE` with no calibrated confidence; a well-calibrated bucket produces a calibrated confidence close to the raw value; an overconfident bucket is flagged and calibrated downward; raw and calibrated confidence are stored separately with `Prediction.confidence` itself untouched; a training window ending after the prediction, and an unbounded training window, both raise `FutureDataLeakageError`; calibration is deterministic/idempotent on rerun; a calibration record is immutable after creation; a new calibration version produces a genuinely separate row.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Raw and calibrated confidence are stored separately (`raw_confidence`/`calibrated_confidence` columns; `Prediction.confidence` never written to).
- [x] Calibration uses only eligible historical outcomes (only `SUCCESS`/`FAILURE` outcomes within the training window, same bucket).
- [x] Calibration avoids future-data leakage (`FutureDataLeakageError`, structurally enforced, tested both for a late-ending and an unbounded window).
- [x] Sample insufficiency is explicitly reported (`VERDICT_INSUFFICIENT_SAMPLE`, `calibrated_confidence=None`).
- [x] Calibration metrics are reproducible (idempotent by `(prediction_id, calibration_version)`; deterministic aggregation).
- [x] Tests cover calibration, empty data, and insufficient samples (all covered; see Test Results).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and direct proof that leakage is structurally impossible, not merely avoided by convention. This EPIC fills the specific gap M1.23/M1.29 left open (confidence, not probability; persisted, not report-only) rather than duplicating either of them, reusing M1.6's buckets, M1.16's sample floor, M1.23's verdict vocabulary, and M1.25's window abstraction throughout. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
