# EPIC-045 — Confidence Quality & Reliability

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1  
**Dependency:** EPIC-044

## Objective
Tell users how trustworthy a confidence percentage is by combining calibration quality, sample size, comparable historical evidence, and data quality.

## Scope
- Confidence quality classification: HIGH, MEDIUM, LOW, INSUFFICIENT_DATA.
- Sample-size evidence.
- Calibration quality.
- Comparable historical setup count.
- Data freshness/completeness.
- Explain why confidence quality has its classification.

## Acceptance Criteria
- Confidence quality is separate from prediction confidence.
- A high confidence with weak evidence cannot receive HIGH quality.
- Insufficient samples are explicitly surfaced.
- Quality calculation is deterministic and versioned.
- User-facing explanation is available.
- Tests cover boundary and insufficient-data cases.

## Dependency Chain
EPIC-044 → EPIC-045 → EPIC-047+

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-045

### Branch

autonomous/epic-m1-50, branched cleanly from `main` (the declared dependency -- EPIC-044 -- is already merged).

### Objective

Tell users how trustworthy a confidence percentage is by combining calibration quality, sample size, comparable historical evidence, and data quality -- never as a function of the raw confidence value itself.

### Design

`classify_confidence_quality` combines three evidence signals, all sourced from already-merged modules:
- **Calibration quality**: EPIC-044's `ConfidenceCalibrationRecord.verdict` (`WELL_CALIBRATED` vs. `OVERCONFIDENT`/`UNDERCONFIDENT`/`INSUFFICIENT_SAMPLE`).
- **Sample-size / comparable historical setup count**: `ConfidenceCalibrationRecord.sample_count` -- this *is* the comparable-historical-setup count (scope item), reused rather than computed a second time. A "strong" sample is `>= STRONG_SAMPLE_MULTIPLIER (2) × MIN_SAMPLE_SIZE_FOR_COMPARISON` (EPIC-019); merely "adequate" is between the two thresholds.
- **Data freshness/completeness**: EPIC-030's `check_market_data_freshness`, reused unchanged.

### Classification Rule (Deterministic, Versioned)

1. `calibration_record.verdict == INSUFFICIENT_SAMPLE` → `INSUFFICIENT_DATA` immediately (AC: "insufficient samples are explicitly surfaced").
2. Otherwise, `HIGH` requires all three: well-calibrated, strong sample, and fresh data.
3. `MEDIUM` requires well-calibrated and fresh data, but not a strong (only adequate) sample.
4. Everything else evidenced but short of `MEDIUM`/`HIGH` is `LOW`.

None of these branches ever reference `prediction.confidence`'s own magnitude (AC: "confidence quality is separate from prediction confidence"; "a high confidence with weak evidence cannot receive HIGH quality") -- `test_high_confidence_with_weak_evidence_cannot_be_high_quality` proves this directly with a `0.99` raw confidence and zero supporting evidence, which classifies `INSUFFICIENT_DATA`.

### Explanation

Every classification stores a `reasons` list (JSON) of the concrete, human-readable evidence statements that produced it -- comparable historical setup count and whether it's strong/adequate, the calibration verdict and its error, and the data-freshness state (scope: "explain why confidence quality has its classification"; AC: "user-facing explanation is available").

### Immutability & Versioning

One row per `(prediction_id, classification_rule_version)`, unique-constrained, idempotent, and guarded by a `before_update` immutability trigger (`ConfidenceQualityImmutableError`) -- a different `classification_rule_version` produces a genuinely separate row rather than mutating a past classification (AC: "quality calculation is deterministic and versioned").

### Files Changed

- `app/confidence_quality.py` — new: `classify_confidence_quality`, `get_confidence_quality`, quality-level constants, `ConfidenceQualityImmutableError`.
- `app/models.py` — new `ConfidenceQualityClassification` model.
- `migrations/versions/0035_confidence_quality.py` — new migration.
- `tests/test_confidence_quality.py` — new: 9 tests.
- `docs/epics/EPIC-045-confidence-quality-reliability.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_confidence_quality.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0035_confidence_quality`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0034` through `0035` (verified `confidence_quality_classifications` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **443 passed, 0 failed** (434 pre-existing from `main` + 9 new).
- `pytest -q tests/test_confidence_quality.py -v`: **9 passed** — insufficient sample yields `INSUFFICIENT_DATA`; a `0.99` raw confidence with zero supporting evidence still classifies `INSUFFICIENT_DATA`, never `HIGH`; strong, well-calibrated, fresh evidence yields `HIGH`; an adequate-but-not-strong sample yields `MEDIUM`; an overconfident calibration yields `LOW` despite a strong sample; stale market data prevents `HIGH` even with strong calibration; classification is deterministic/idempotent on rerun; a classification row is immutable after creation; a new classification version produces a genuinely separate row.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Confidence quality is separate from prediction confidence (never read in any classification branch; proven by test).
- [x] A high confidence with weak evidence cannot receive HIGH quality (proven directly by test with `confidence=0.99`).
- [x] Insufficient samples are explicitly surfaced (`QUALITY_INSUFFICIENT_DATA`, reused from EPIC-044's own `INSUFFICIENT_SAMPLE` verdict).
- [x] Quality calculation is deterministic and versioned (idempotent by `(prediction_id, classification_rule_version)`).
- [x] User-facing explanation is available (`reasons` list on every classification).
- [x] Tests cover boundary and insufficient-data cases (adequate-vs-strong sample boundary, insufficient-data, all four quality levels).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a direct proof that a very high raw confidence with no supporting evidence still cannot receive `HIGH` quality. This EPIC composes EPIC-044's calibration record and EPIC-030's freshness check without duplicating either, and introduces no new evidence-gathering logic of its own -- it only classifies evidence already produced elsewhere. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
