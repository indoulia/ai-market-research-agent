# EPIC-M1.56 — Adaptive Recommendation Adjustment

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1  
**Dependency:** M1.22, M1.23, M1.29, M1.41, M1.53, M1.55

## Objective
Generate evidence-backed candidate adjustments to recommendation scores, confidence, target, SL, or selection rules using validated historical patterns.

## Scope
- Identify recurring under/over-performance patterns.
- Generate candidate adjustments with evidence and sample size.
- Compare current vs candidate behavior on historical data.
- Preserve current production rules until promotion.
- Version every candidate adjustment.

## Acceptance Criteria
- Candidate adjustments are never applied directly to production.
- Each candidate includes rationale, affected conditions, expected impact, sample size, and validation evidence.
- Historical replay compares baseline and candidate.
- Candidates with insufficient evidence are rejected or marked pending.
- Reproducible candidate evaluation is tested.

## Dependency Chain
M1.22/M1.23/M1.29/M1.41/M1.53/M1.55 → M1.56 → M1.57

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.56

### Branch

autonomous/epic-m1-56, branched cleanly from `main` (all six declared dependencies -- M1.22, M1.23, M1.29, M1.41, M1.53, M1.55 -- are already merged).

### Objective

Generate evidence-backed candidate adjustments to recommendation scores, confidence, target, SL, or selection rules using validated historical patterns -- never applying any of them to production.

### Design

`generate_adaptive_adjustment_candidates` synthesizes three already-existing "candidate signal" sources into one unified `AdaptiveAdjustmentCandidate` shape, none of them modified:
- **`PROBABILITY_CALIBRATION`** — M1.29's `build_calibration_candidate`, flagging `OVERCONFIDENT`/`UNDERCONFIDENT` probability buckets, validated strictly out-of-sample via M1.29's own `evaluate_calibration_candidate_out_of_sample`.
- **`REGIME_SCORE_ADJUSTMENT`** — M1.41's `build_regime_score_adjustment_candidate`, flagging miscalibrated regimes, validated via M1.41's own `evaluate_regime_score_adjustment_out_of_sample`.
- **`FEEDBACK_LEARNING_SIGNAL`** — M1.53's `compute_feedback_learning_signals`, flagging `WEAK` feedback category/reason patterns. These have no out-of-sample validation mechanism of their own, so they are always surfaced `PENDING` rather than a fabricated validation -- an honest limitation, not an oversight (AC: "candidates with insufficient evidence are ... marked pending").

### Candidate Shape

Every candidate carries `rationale` (human-readable), `affected_condition` (the specific bucket/regime/feedback category+reason), `expected_impact` (the underlying signal's magnitude), `sample_size`, and `validation_status`/`validation_detail` (AC: "each candidate includes rationale, affected conditions, expected impact, sample size, and validation evidence").

### Historical Replay / Out-of-Sample Validation

For the two signal types with a real out-of-sample mechanism (calibration, regime), the underlying source module's own comparison is reused directly -- `IMPROVED` → `VALIDATED`, `NOT_IMPROVED` → `REJECTED`, anything else (insufficient evidence in either window) → `PENDING` (AC: "historical replay compares baseline and candidate"; "candidates with insufficient evidence are rejected or marked pending").

### Never Applied to Production

This module has no write path to `Prediction`, `ScanCandidate`, or any scoring/selection table at all (AC: "candidate adjustments are never applied directly to production"), proven directly by `test_candidates_never_write_to_predictions`. Promoting a `VALIDATED` candidate remains a decision for a future promotion-gate EPIC (M1.57), the same "propose here, gate there" split M1.29/M1.30 already have with M1.31, and M1.43 has with M1.44.

### Versioning & Reproducibility

Every candidate and the report itself carry `ADAPTIVE_ADJUSTMENT_VERSION` (AC: "version every candidate adjustment"). The whole pipeline is a pure aggregation over M1.29/M1.41/M1.53's own already-deterministic outputs with no randomness anywhere -- `test_report_generation_is_reproducible` proves calling it twice on identical data yields an identical report.

### Files Changed

- `app/adaptive_recommendation_adjustment.py` — new: `generate_adaptive_adjustment_candidates`, `AdaptiveAdjustmentCandidate`/`AdaptiveAdjustmentReport` dataclasses, source/status constants.
- `tests/test_adaptive_recommendation_adjustment.py` — new: 6 tests.
- `docs/epics/EPIC-M1.56-adaptive-recommendation-adjustment.md` — this completion report.

No migration: pure read-side synthesis of three already-existing candidate-signal sources.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_adaptive_recommendation_adjustment.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0038_recommendation_revisions`, unchanged -- confirms no migration drift)

### Test Results

- `pytest -q`: **494 passed, 0 failed** (488 pre-existing from `main` + 6 new).
- `pytest -q tests/test_adaptive_recommendation_adjustment.py -v`: **6 passed** — no evidence produces no candidates; an overconfident calibration pattern that persists out-of-sample is `VALIDATED`; a regime miscalibration pattern produces exactly one candidate with the correct sample size; a weak feedback signal (`TOO_HIGH` correlating with failures, distinct from an `AGREE` baseline on successes) is surfaced `PENDING`; candidates never write to `Prediction`; report generation is reproducible across two identical calls.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: passed, single head unchanged (no migration in this EPIC).

### Acceptance Criteria

- [x] Candidate adjustments are never applied directly to production (no write path exists in this module at all; proven by test).
- [x] Each candidate includes rationale, affected conditions, expected impact, sample size, and validation evidence (all fields populated on every candidate).
- [x] Historical replay compares baseline and candidate (reuses M1.29/M1.41's own out-of-sample comparisons).
- [x] Candidates with insufficient evidence are rejected or marked pending (`STATUS_REJECTED`/`STATUS_PENDING`, including an honest `PENDING` for feedback signals with no validation mechanism).
- [x] Reproducible candidate evaluation is tested (`test_report_generation_is_reproducible`).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence, including a direct proof that generating candidates never writes to `Prediction` and that the same inputs always reproduce the identical report. This EPIC composes M1.29/M1.41/M1.53's existing candidate-signal machinery into one unified, versioned shape without duplicating or modifying any of them, and is honest about the one signal type (feedback) that has no out-of-sample validation mechanism yet rather than fabricating one. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
