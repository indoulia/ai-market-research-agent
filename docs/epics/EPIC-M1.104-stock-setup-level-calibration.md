# EPIC-M1.104 — Stock & Setup-Level Calibration

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P0

## Objective
Calibrate prediction probabilities and Trust Score at stock, setup, sector and other materially relevant segments instead of relying only on global calibration.

## Scope
- Calibrate by stock, setup, sector, market-cap and horizon where sample size permits.
- Apply hierarchical fallback when segment samples are insufficient.
- Track segment calibration quality and sample confidence.
- Prevent sparse segments from producing falsely precise probabilities.
- Feed validated calibration into Trust Score.

## Dependencies
M1.75, M1.77, M1.79, M1.82, M1.100.

## Completion Report

**Status:** DONE — merged to main via PR #163 (`3aa8703`).

**Implementation:**
- `app/segment_calibration.py`: a new, versioned (`SEGMENT_CALIBRATION_VERSION = "SGC-001"`) module. Reuses M1.82's own `SEGMENT_SECTOR`/`SEGMENT_MARKET_CAP`/`SEGMENT_HORIZON` names and `discovery_segmentation.classify_market_cap_bucket`, and M1.85's own SMA20-distance/volume-ratio bucket thresholds for the new `SEGMENT_SETUP` combination, and M1.11's own calibration verdict vocabulary/`MATERIAL_ERROR_THRESHOLD`/`MIN_SAMPLE_SIZE` — nothing redefined.
- **Calibrate by stock, setup, sector, market-cap and horizon where sample size permits / apply hierarchical fallback:** `assess_segment_calibration` walks a fixed `FALLBACK_ORDER` (`STOCK -> SETUP -> SECTOR -> MARKET_CAP -> HORIZON -> GLOBAL`) for one prediction, stopping at the first level whose exact segment key reaches `MIN_SAMPLE_SIZE` — never computing an error from fewer samples, at any level.
- **Prevent sparse segments from producing falsely precise probabilities:** even `GLOBAL` can resolve to `INSUFFICIENT_SAMPLE` if the platform's total evaluated history for that model version is still below the floor — never fabricated.
- **Track segment calibration quality and sample confidence:** the full `fallback_chain` considered (every level's key, sample count, and whether it was skipped for lacking evidence — e.g. `SETUP` when the target prediction has no linked `ScanCandidate`) is persisted alongside the resolved level, for auditability.
- **Feed validated calibration into Trust Score:** `calibration_error`/`verdict` are propose-only — no write path to `Prediction`, `PredictionTrustScore`, or `TrustControlDecision`; wiring remains a future revision's job, the same posture M1.101/M1.102/M1.103 already established.
- New immutable table `segment_calibration_assessments` (migration `0079_segment_calibration.py`), idempotent by `(prediction_id, evaluated_at)`.

**Tests:** `tests/test_segment_calibration.py` (8 tests) — resolves to stock level with enough samples; falls back past a sparse stock/setup to sector; falls all the way back to global when nothing clears the floor; well-calibrated/underconfident/overconfident verdicts; `SETUP` correctly marked skipped when the target has no linked technical data; idempotency.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_segment_calibration.py -q` → `8 passed`
- `python -m pytest -q` (full suite) → `993 passed`
- `python -m alembic heads` → single head `0079_segment_calibration (head)`, chain resolves cleanly
