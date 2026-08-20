# EPIC-M1.29 — Adaptive Score Calibration

**Status:** APPROVED  
**Execution Status:** VALIDATING  
**Priority:** P1

## Objective
Use completed recommendation outcomes to measure and calibrate score/probability reliability without changing the production scoring model automatically.

## Scope
- Compare predicted probability/score bands with observed success.
- Calculate calibration error by horizon and regime.
- Detect persistent over-confidence or under-confidence.
- Produce a versioned calibration candidate.
- Preserve original recommendation scores unchanged.

## Non-goals
- Automatic production model replacement.
- Backfilling scores on historical recommendations.
- Trading decisions.

## Acceptance Criteria
- Calibration uses only closed outcomes.
- Historical scores remain immutable.
- Calibration results are reproducible and versioned.
- Minimum sample thresholds are enforced.
- Candidate calibration can be compared with current calibration out-of-sample.

## Dependency Chain
**Previous:** M1.22, M1.23, M1.26, M1.27  
**Next:** M1.30, M1.31

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.29

### Branch

autonomous/epic-m1-29, branched cleanly from `main` (all four declared dependencies -- M1.22, M1.23, M1.26, M1.27 -- are already merged).

### Objective

Use completed recommendation outcomes to measure calibration error and propose a versioned, testable calibration adjustment, without ever changing any production score automatically.

### Design Decisions

- **No new table or migration.** Read-only aggregation and a pure-function candidate object; nothing here writes to `Prediction` or any other table (scope item 5, "preserve original recommendation scores unchanged," and AC "historical scores remain immutable" both hold structurally, not by convention alone).
- **`build_calibration_candidate(session, training_window) -> CalibrationCandidate`** derives a per-bucket calibration offset (`-calibration_error`) from a training window's closed outcomes only (AC: "calibration uses only closed outcomes"), using the exact same ten fixed-width probability buckets M1.6 defines and the exact calibration-verdict vocabulary M1.23 already established (`OVERCONFIDENT`/`UNDERCONFIDENT`/`WELL_CALIBRATED`/`INSUFFICIENT_SAMPLE`, imported not redefined).
- **`apply_calibration_candidate(candidate, predicted_probability) -> Decimal`** is a pure function returning a new adjusted value -- it never mutates a `Prediction`. A bucket without enough training-window samples (`INSUFFICIENT_SAMPLE`) is explicitly *not* adjusted, falling back to the raw value, satisfying "minimum sample thresholds are enforced" at the point where a threshold actually matters (the adjustment itself), not only in a report.
- **`evaluate_calibration_candidate_out_of_sample(session, candidate, evaluation_window)`** is the AC's central requirement ("candidate calibration can be compared with current calibration out-of-sample"): it computes mean absolute calibration error (|predicted − actual|, actual ∈ {0,1}) twice over the *same* out-of-sample window -- once with raw `predicted_probability`, once with the candidate's adjustment -- and compares them. Reuses M1.25's `EvaluationWindow`/`OverlappingEvaluationWindowsError` directly: an evaluation window overlapping the candidate's own training window is a hard error, since an out-of-sample test must never reuse training evidence.
- **`IMPROVEMENT_MARGIN = Decimal("0.02")`** (fixed, documented, versioned via `CALIBRATION_CANDIDATE_VERSION`): the candidate must reduce mean absolute error by at least this much, out-of-sample, to be called `IMPROVED` rather than `NOT_IMPROVED` -- proven by two tests: one where the training-window miscalibration pattern genuinely persists out-of-sample (`IMPROVED`), and one where it doesn't generalize (`NOT_IMPROVED`, since the training-derived offset would make an already-well-calibrated out-of-sample population worse).
- **Horizon segmentation is fully covered** (`by_horizon`, all four `VALID_HORIZON_DAYS` always present). **Regime segmentation is measurement-only, reported "where available"** (a `MarketRegime` row exists only for explicitly classified scans, M1.26) -- the candidate's actual probability adjustment in this first version is neither horizon- nor regime-conditional, only bucket-conditional; that is a documented scope simplification, not an omission, open to a future EPIC extending it.
- **Promoting a calibration candidate to production is explicitly out of scope** (non-goal: "automatic production model replacement") -- this EPIC only measures and proposes; any promotion mechanism belongs to a separately approved, evidence-gated EPIC (conceptually M1.31, once real).

### Files Changed

- `app/adaptive_calibration.py` — new: `build_calibration_candidate`, `apply_calibration_candidate`, `evaluate_calibration_candidate_out_of_sample`, `CalibrationCandidate`, `BucketCalibration`, `HorizonCalibrationBuckets`, `RegimeCalibrationMetric`, `CalibrationComparisonResult`, version/margin constants.
- `tests/test_adaptive_calibration.py` — new: 8 tests.
- `docs/epics/EPIC-M1.29-adaptive-score-calibration.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_adaptive_calibration.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (no migration added by this EPIC; head unchanged from M1.26's `0021_market_regimes`)

### Test Results

- `pytest -q`: **270 passed, 0 failed** (262 pre-existing from `main` + 8 new).
- `pytest -v tests/test_adaptive_calibration.py`: **8 passed** — a systematically overconfident training bucket (predicts 0.95, only 20% succeed) produces a positive calibration error and a real downward adjustment; a bucket with only 3 training samples is left unadjusted regardless of its apparent error; an evaluation window overlapping the training window raises `OverlappingEvaluationWindowsError`; an out-of-sample window with too few samples is `INSUFFICIENT_SAMPLE` with no error computed; a candidate whose training-window miscalibration genuinely persists out-of-sample reduces mean absolute error and is `IMPROVED`; a candidate applied to an out-of-sample population that turns out to already be well-calibrated is correctly `NOT_IMPROVED`; the horizon breakdown always reports all four supported horizons; and regime calibration is reported only for a scan that was actually classified.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: unchanged, single head `0021_market_regimes` (no migration in this EPIC).

### Acceptance Criteria

- [x] Calibration uses only closed outcomes (`_evaluated_in_window` filters to `SUCCESS`/`FAILURE` only).
- [x] Historical scores remain immutable (no write path anywhere in this module).
- [x] Calibration results are reproducible and versioned (`CALIBRATION_CANDIDATE_VERSION`, plain deterministic aggregation).
- [x] Minimum sample thresholds are enforced (both in verdict reporting and in whether an offset is actually applied).
- [x] Candidate calibration can be compared with current calibration out-of-sample (`evaluate_calibration_candidate_out_of_sample`, proven by both the `IMPROVED` and `NOT_IMPROVED` tests).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence, including a genuine out-of-sample generalization test in both directions (improves / doesn't improve). The decision to keep the candidate's actual adjustment bucket-conditional only (not horizon/regime-conditional) is a documented scope simplification for reviewer scrutiny. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
