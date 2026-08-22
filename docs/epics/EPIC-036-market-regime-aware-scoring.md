# EPIC-036 — Market-Regime-Aware Scoring

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Make scoring sensitive to measurable market conditions when historical evidence proves that prediction behavior changes across regimes.

## Scope
- Define deterministic market regimes.
- Attach regime at recommendation time.
- Measure score/outcome performance by regime.
- Evaluate regime-specific score adjustments.
- Preserve a regime-neutral baseline for comparison.
- Avoid regime classification using future information.

## Acceptance Criteria
- [ ] Every eligible recommendation has a point-in-time regime classification.
- [ ] Regime definitions are versioned.
- [ ] Regime-specific performance is measurable.
- [ ] Regime-aware scoring is compared against the baseline out-of-sample.
- [ ] No regime adjustment is enabled without evidence.
- [ ] Historical recommendations retain their original regime and score.

## Dependencies
**Previous:** EPIC-021, EPIC-035
**Next:** EPIC-037

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-036

### Branch

autonomous/epic-m1-41, branched cleanly from `main` (both declared dependencies -- EPIC-021 and EPIC-035 -- are already merged).

### Objective

Make recommendation scoring sensitive to market regime only where historical evidence shows the regime-neutral score is systematically miscalibrated within that specific regime -- never automatically, never on in-sample evidence alone, and never by mutating the original score or regime.

### Regime Definitions

Reuses EPIC-021's `classify_market_regime` unchanged: a deterministic, versioned (`REGIME_RULE_VERSION = "REG-001"`) breadth/volatility classification (`BULLISH`/`BEARISH`/`NEUTRAL` × `HIGH_VOL`/`LOW_VOL`) computed only from that scan's own `ScanCandidate.sma20_distance`/`atr_percent` -- values already point-in-time-safe by EPIC-015's own construction. No new regime taxonomy is introduced.

### Leakage Controls

Every prediction analyzed traces back to the exact `ScanCandidate`/scan it was generated from (`Prediction → RecommendationGeneration → ScanCandidate.scan_id`), and `classify_market_regime` classifies strictly from that scan's own candidates -- there is no code path that reads a later scan, a later price, or the outcome itself into the regime label (AC: "avoid regime classification using future information", inherited unmodified from EPIC-021).

### Universal Point-in-Time Coverage (AC1)

Unlike prior EPICs' "where available" regime segmentation (EPIC-024, EPIC-034), this module calls `classify_market_regime` on demand for every prediction's own scan rather than only reading an already-populated `MarketRegime` row. Since a prediction only exists for an *eligible* `ScanCandidate`, and `classify_market_regime` only raises when a scan has zero eligible candidates, classification always succeeds -- every eligible recommendation analyzed by this module gets a real, point-in-time regime classification, not a partial one (AC: "every eligible recommendation has a point-in-time regime classification").

### Evaluation Methodology

1. `analyze_regime_performance` segments closed (`SUCCESS`/`FAILURE`) outcomes by regime over a training `EvaluationWindow` (EPIC-074), measuring each regime's average normalized `opportunity_score` vs. observed success rate. A regime's calibration error must clear `MIN_SAMPLE_SIZE_FOR_COMPARISON` (EPIC-019, 20) to receive anything other than `INSUFFICIENT_SAMPLE`; otherwise it is `OVERCONFIDENT`/`UNDERCONFIDENT`/`WELL_CALIBRATED` per EPIC-024's existing calibration vocabulary and `CALIBRATION_ERROR_MARGIN` (EPIC-072, reused unchanged).
2. `build_regime_score_adjustment_candidate` proposes a per-regime score offset **only** for regimes verdicted `OVERCONFIDENT`/`UNDERCONFIDENT` -- a `WELL_CALIBRATED` or `INSUFFICIENT_SAMPLE` regime is left out of `regime_offsets` entirely and silently falls back to the regime-neutral baseline when applied (AC: "no regime adjustment is enabled without evidence", "weak or unstable evidence results in no change" carried over from this platform's established pattern).
3. `evaluate_regime_score_adjustment_out_of_sample` tests the candidate strictly out-of-sample: it returns `NO_ADJUSTMENT_ELIGIBLE` immediately if no regime ever cleared the evidence threshold; otherwise it rejects (`OverlappingEvaluationWindowsError`) any evaluation window overlapping the training window, requires the evaluation window to independently clear the sample floor, and compares the candidate's mean absolute error against the regime-neutral baseline's MAE over that unseen window (AC: "regime-aware scoring is compared against the baseline out-of-sample"). `IMPROVED` requires beating the baseline by at least `IMPROVEMENT_MARGIN` (0.02); otherwise `NOT_IMPROVED`.

### Comparative Results

`test_candidate_that_generalizes_out_of_sample_beats_the_baseline` proves a concrete before/after: a regime with a stable, deliberately induced miscalibration (score implies ~35% success, actual win rate 12.5%) in the training window, when the identical pattern recurs out-of-sample, verdicts `IMPROVED` -- the candidate's MAE is provably lower than the regime-neutral baseline's MAE on unseen data.

### Whether Regime-Aware Scoring Was Enabled or Rejected

This EPIC delivers the measurement, candidate-building, and out-of-sample comparison mechanism itself -- it does not wire any candidate into the live scoring path used by `app/scoring.py` (EPIC-009) or recommendation generation, matching this platform's established non-goal of "no automatic production model/score replacement" (same posture EPIC-024, EPIC-025, EPIC-035 took). Enabling a regime-aware adjustment in production is a decision for a future promotion-gate EPIC (EPIC-039/EPIC-052 in the backlog), exactly as EPIC-026 gates calibration/model promotion today.

### Original Score & Regime Immutability

`app/scoring.py` and `app/market_regime.py` are not modified. `apply_regime_score_adjustment` returns a new Decimal and never writes to `Prediction.opportunity_score` or `MarketRegime.regime`. `test_original_score_and_regime_are_never_mutated` proves this directly by snapshotting every `Prediction.opportunity_score` before and after building and applying a candidate (AC: "historical recommendations retain their original regime and score").

### Design Decisions

- **Reuses rather than duplicates**: EPIC-021's `classify_market_regime` (regime definitions), EPIC-072/EPIC-024's calibration verdict vocabulary and `CALIBRATION_ERROR_MARGIN` (evidence-gating language), EPIC-019's `MIN_SAMPLE_SIZE_FOR_COMPARISON`, and EPIC-074's `EvaluationWindow`/`OverlappingEvaluationWindowsError` (disjoint train/evaluate). No existing module is modified.
- **Per-regime gating, not all-or-nothing**: unlike EPIC-035 (which requires every score component to clear the evidence floor before any candidate is eligible), this EPIC gates independently per regime -- a rare regime with insufficient evidence simply has no offset while a well-evidenced regime can still get one, since regimes are naturally uneven in frequency and forcing universal coverage would block adjustment for common regimes indefinitely.

### Files Changed

- `app/regime_aware_scoring.py` — new: `analyze_regime_performance`, `build_regime_score_adjustment_candidate`, `apply_regime_score_adjustment`, `evaluate_regime_score_adjustment_out_of_sample`, `RegimePerformance`/`RegimeScoreAdjustmentCandidate`/`RegimeScoreComparisonResult` dataclasses.
- `tests/test_regime_aware_scoring.py` — new: 10 tests.
- `docs/epics/EPIC-036-market-regime-aware-scoring.md` — this completion report.

No migration: pure comparison/analysis logic over existing tables, matching EPIC-024/EPIC-025/EPIC-035's precedent.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_regime_aware_scoring.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0028_historical_learning_records`, unchanged -- confirms no migration drift)

### Test Results

- `pytest -q`: **356 passed, 0 failed** (346 pre-existing from `main` + 10 new).
- `pytest -q tests/test_regime_aware_scoring.py -v`: **10 passed** — every evaluated prediction gets a point-in-time regime; an insufficient-sample regime is not eligible for an offset; a stable, deliberately induced miscalibration produces an eligible `OVERCONFIDENT` offset; a well-calibrated regime gets no offset; a regime without an eligible offset returns the unadjusted score unchanged; out-of-sample evaluation with no eligible regimes returns `NO_ADJUSTMENT_ELIGIBLE` without a query; overlapping windows raise `OverlappingEvaluationWindowsError`; an evaluation window with insufficient sample yields `INSUFFICIENT_SAMPLE`; a candidate that generalizes out-of-sample verdicts `IMPROVED` with a real baseline/candidate MAE comparison; the original score and regime are provably untouched after building and applying a candidate.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: passed, single head unchanged (no migration in this EPIC).

### Acceptance Criteria

- [x] Every eligible recommendation has a point-in-time regime classification (`classify_market_regime` called on demand per prediction's own scan; always succeeds for an eligible candidate's scan).
- [x] Regime definitions are versioned (`REGIME_RULE_VERSION`, unchanged from EPIC-021).
- [x] Regime-specific performance is measurable (`analyze_regime_performance`, per-regime sample count/score/success rate/calibration error/verdict).
- [x] Regime-aware scoring is compared against the baseline out-of-sample (`evaluate_regime_score_adjustment_out_of_sample`, strict disjoint-window MAE comparison).
- [x] No regime adjustment is enabled without evidence (`regime_offsets` only populated for `OVERCONFIDENT`/`UNDERCONFIDENT` regimes clearing the sample floor).
- [x] Historical recommendations retain their original regime and score (`app/scoring.py`/`app/market_regime.py` untouched; proven by direct before/after snapshot test).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a direct proof that the original score and regime are never mutated and a genuine out-of-sample MAE comparison showing a real, induced miscalibration correcting itself out-of-sample. This EPIC composes EPIC-021's regime classification, EPIC-019/EPIC-072/EPIC-024's evidence-gating vocabulary, and EPIC-074's disjoint-window abstraction rather than duplicating any of them, and deliberately does not enable any adjustment in the live scoring path -- that remains a future promotion-gate decision. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->