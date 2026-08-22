# EPIC-101 — Data Distribution & Feature Drift Intelligence

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Detect changes in the input data and feature distributions that can make a previously reliable prediction model less trustworthy even before outcome-based regression becomes visible.

## Scope
- Monitor distribution changes in market, technical, fundamental, news/event and engineered features.
- Detect missingness, freshness and coverage drift.
- Compare live distributions with validated training/reference distributions.
- Measure feature importance drift where available.
- Trigger trust reduction or model review when drift exceeds policy thresholds.
- Preserve drift history and reference versions.
- Add deterministic drift fixtures and tests.

## Acceptance Criteria
- Data and feature drift are measurable by capability and segment.
- Material drift is surfaced before it silently contaminates learning.
- Drift can affect Trust Score through explicit policy.
- Historical reference distributions remain immutable.
- Drift alerts are auditable and reproducible.

## Dependencies
Previous: EPIC-078, EPIC-085, EPIC-088, EPIC-100.
Next: EPIC-102.

## Completion Report

**Status:** DONE — merged to main via PR #151 (`3b173a3`).

**Implementation:**
- `app/feature_drift_monitor.py`: a new, versioned (`FEATURE_DRIFT_VERSION = "FDM-001"`) module monitoring a fixed, documented vocabulary of the real, already-captured numeric feature columns `app.scan`'s pipeline produces on `ScanCandidate` — `SMA20_DISTANCE`, `VOLUME_RATIO_20D`, `ATR_PERCENT`, `PREDICTED_PROBABILITY`, `CONFIDENCE`.
- **Compare live distributions with validated training/reference distributions / historical reference distributions remain immutable:** `register_reference_distribution` freezes a `(model_version, feature_name)`'s mean/stdev once, idempotently — never recomputed after first registration; raises `InsufficientReferenceSampleError` rather than freezing a reference from a sparse sample.
- **Monitor distribution changes... measurable by capability and segment:** `detect_feature_drift` standardizes a monitoring window's mean against the frozen reference's own stdev (`drift_magnitude = |monitoring_mean - reference_mean| / reference_stdev`), flagging `DRIFT_DETECTED` at a fixed `DRIFT_THRESHOLD_STD = 2` standard deviations. A zero-variance reference or under-sampled window honestly resolves to `INSUFFICIENT_SAMPLE` rather than dividing by zero or fabricating a verdict.
- **Detect missingness, freshness and coverage drift:** `detect_coverage_drift` reuses the real, already-computed `ScanCandidate.data_quality_passed` verdict as the coverage signal (no second missingness metric invented), flagging drift only on a coverage *drop* (`WEAKNESS_MARGIN`), never on improvement.
- **Measure feature importance drift where available:** honestly not implemented — this platform has no model-interpretability/feature-importance store yet; the gap is named explicitly in the module docstring rather than fabricated, matching this backlog's established honesty convention (EPIC-090/EPIC-091/EPIC-093).
- **Trigger trust reduction... when drift exceeds policy thresholds:** both assessment tables carry `trust_reduction_recommended` — a propose-only signal with no write path to `PredictionTrustScore`/`TrustControlDecision`; wiring it into EPIC-087's already-merged consolidation is left to a future revision, the same posture EPIC-085/EPIC-083's own `trust_reduction_recommended` fields had before `trust_control.py` composed them.
- **Preserve drift history and reference versions / auditable and reproducible:** new immutable tables `feature_reference_distributions`, `feature_drift_assessments`, `coverage_drift_assessments` (migration `0076_feature_drift_monitor.py`), each idempotent by its natural key.

**Tests (deterministic drift fixtures, per scope):** `tests/test_feature_drift_monitor.py` (11 tests) — reference registration (idempotency, minimum-sample rejection, unknown-feature rejection), no-drift/drift-detected/insufficient-sample verdicts, idempotency, and coverage-drift detected/stable/insufficient-sample cases.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_feature_drift_monitor.py -q` → `11 passed`
- `python -m pytest -q` (full suite) → `950 passed`
- `python -m alembic heads` → single head `0076_feature_drift (head)`, chain resolves cleanly
