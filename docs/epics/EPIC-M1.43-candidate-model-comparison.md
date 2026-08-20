# EPIC-M1.43 — Candidate Model Comparison

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Compare a candidate prediction/scoring model against the current production model using identical historical evaluation rules.

## Scope
- Define comparable model interfaces.
- Run both models on the same point-in-time dataset.
- Compare success rate, return, calibration, and horizon performance.
- Compare by market regime and discovery segment.
- Record statistical/sample-size limitations.
- Produce a reproducible comparison report.

## Acceptance Criteria
- [ ] Both models receive identical eligible inputs.
- [ ] No future information leaks into either model.
- [ ] Metrics use identical outcome definitions.
- [ ] Comparison includes overall and horizon-level performance.
- [ ] Comparison includes relevant market/segment breakdowns.
- [ ] Insufficient evidence is explicitly reported.
- [ ] Candidate is not promoted by this EPIC.

## Dependencies
**Previous:** M1.30, M1.39, M1.41, M1.42
**Next:** M1.44

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.43

### Branch

autonomous/epic-m1-43, branched cleanly from `main` (all four declared dependencies -- M1.30, M1.39, M1.41, M1.42 -- are already merged).

### Objective

Compare a candidate prediction/scoring model against the current production model using identical historical evaluation rules -- running both models on the *same* point-in-time dataset (unlike M1.30, which compares the same model across two disjoint time periods).

### Model Versions

`production_model` (version `CMC-001`, this module's own) always returns the historical pipeline's own recorded `predicted_probability` -- never recomputed, so it carries zero leakage risk beyond what M1.39 already guarantees. The candidate is any caller-supplied `Callable[[HistoricalLearningRecord], Decimal]` (AC: "define comparable model interfaces"). This repo still has no second, real production-quality candidate model -- the same honest caveat M1.25/M1.29/M1.30/M1.40 already documented -- but the comparison machinery itself is genuinely usable today with any candidate function, real or synthetic.

### Dataset Version

`compare_candidate_model` takes an explicit `dataset_version` and calls M1.39's `build_learning_dataset`/`get_learning_dataset` to obtain the single common set of `HistoricalLearningRecord` rows (filtered to `included=True`) both models are evaluated against -- literally the same rows, not two independently-derived query paths (AC: "both models receive identical eligible inputs"). Every feature column on those rows is already point-in-time-safe by M1.39's own construction (AC: "no future information leaks into either model").

### Evaluation Period

Unlike M1.30/M1.29/M1.40/M1.41, this comparison has no training/evaluation window split -- both models see the *same* dataset version's *same* records, since the point of this EPIC is isolating the model's own predictive quality, not a temporal generalization test (that remains M1.30's job for a single model across time, and this module's job for two models across the same time).

### Metrics

For each model: `observed_success_rate`, `average_predicted_probability`, `average_realized_return`, and `mean_absolute_calibration_error` (`|predicted - actual|`, the same MAE definition M1.29/M1.30/M1.40/M1.41 all already use), computed only from `SUCCESS`/`FAILURE` records (AC: "metrics use identical outcome definitions" -- `NEUTRAL`/`INSUFFICIENT_DATA` excluded as non-directional, matching this platform's established convention). Identical breakdowns by horizon, sector, market-cap bucket, discovery source, and market regime are computed for both models from the same grouping code (AC: "comparison includes overall and horizon-level performance"; "comparison includes relevant market/segment breakdowns"). Regime segmentation reuses M1.41's on-demand `classify_market_regime` technique to reach full coverage rather than "where available," even for a record whose frozen `market_regime` column happened to be null at dataset-build time.

### Limitations

Every dimension (`overall` and each segment bucket) below `MIN_SAMPLE_SIZE_FOR_COMPARISON` (M1.16, 20) is listed explicitly in `insufficient_sample_dimensions` (AC: "insufficient evidence is explicitly reported") -- an insufficient overall sample short-circuits the whole report to `VERDICT_INSUFFICIENT_EVIDENCE` before any comparison decision is made.

### Comparison Decision

Reuses M1.30's exact verdict vocabulary (`VERDICT_VALIDATED`/`VERDICT_REGRESSED`/`VERDICT_INSUFFICIENT_EVIDENCE`) and `REGRESSION_MARGIN` (0.10): the candidate is `VALIDATED` unless its overall calibration MAE is worse than production's by at least that margin, in which case it is `VERDICT_REGRESSED`. This module never writes anywhere -- there is no promotion path at all (AC: "candidate is not promoted by this EPIC"), proven directly by `test_no_write_path_exists_for_promotion`.

### Design Decisions

- **Reuses rather than duplicates**: M1.39's `HistoricalLearningRecord`/`build_learning_dataset`/`get_learning_dataset` (the common dataset), M1.41's on-demand regime-classification technique, M1.30's verdict vocabulary and `REGRESSION_MARGIN`, M1.16's `MIN_SAMPLE_SIZE_FOR_COMPARISON`. No existing module is modified.
- **Same-period, two-model comparison is the genuinely new capability vs. M1.30's same-model, two-period comparison** -- both are useful and neither replaces the other; this module is the natural counterpart, not a duplicate.
- **Model interface kept intentionally minimal** (`HistoricalLearningRecord -> Decimal`): any candidate scoring function -- a modified weighting, an M1.40/M1.41-style adjustment, or a genuinely new model -- can be wrapped into this shape by its own caller without this module needing to know anything about how the candidate was built.

### Files Changed

- `app/candidate_model_comparison.py` — new: `compare_candidate_model`, `production_model`, `ModelEvaluation`/`ModelSegmentMetric`/`CandidateModelComparisonReport` dataclasses.
- `tests/test_candidate_model_comparison.py` — new: 6 tests.
- `docs/epics/EPIC-M1.43-candidate-model-comparison.md` — this completion report.

No migration: pure read-side comparison over M1.39's existing dataset.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_candidate_model_comparison.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0028_historical_learning_records`, unchanged -- confirms no migration drift)

### Test Results

- `pytest -q`: **372 passed, 0 failed** (366 pre-existing from `main` + 6 new).
- `pytest -q tests/test_candidate_model_comparison.py -v`: **6 passed** — a small dataset reports `INSUFFICIENT_EVIDENCE` with no calibration delta; a candidate identical to production yields a zero delta and `VALIDATED`; a candidate predicting the opposite of what happened is unambiguously worse and verdicts `REGRESSED`; a candidate that reads the true label directly (an intentionally "perfect" candidate) has a strictly lower MAE than production and verdicts `VALIDATED`; horizon/sector/regime breakdowns are populated identically in shape for both models, with regime reaching full coverage; no `Prediction` row is ever mutated by running a comparison.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: passed, single head unchanged (no migration in this EPIC).

### Acceptance Criteria

- [x] Both models receive identical eligible inputs (same `HistoricalLearningRecord` rows, same `dataset_version`).
- [x] No future information leaks into either model (both operate only on M1.39's already point-in-time-safe frozen columns).
- [x] Metrics use identical outcome definitions (`SUCCESS`/`FAILURE` only, shared `_evaluate_model` logic for both models).
- [x] Comparison includes overall and horizon-level performance (`by_horizon` on both `ModelEvaluation`s).
- [x] Comparison includes relevant market/segment breakdowns (`by_sector`/`by_market_cap_bucket`/`by_discovery_source`/`by_regime`).
- [x] Insufficient evidence is explicitly reported (`insufficient_sample_dimensions`, `VERDICT_INSUFFICIENT_EVIDENCE`).
- [x] Candidate is not promoted by this EPIC (no write path exists in this module at all; proven by test).

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence, including a genuinely worse and a genuinely better synthetic candidate to prove the verdict logic discriminates correctly in both directions. This EPIC composes M1.39's frozen dataset, M1.41's full-coverage regime technique, M1.30's verdict vocabulary, and M1.16's evidence threshold rather than duplicating any of them, and is the natural same-period counterpart to M1.30's same-model, two-period comparison. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->