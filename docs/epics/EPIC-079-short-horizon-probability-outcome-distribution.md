# EPIC-079 — Short-Horizon Probability & Outcome Distribution

**Status:** DONE
**Execution Status:** COMPLETED
**Approved By:** User
**Priority:** P0

## Objective
Extend short-term recommendation outputs from a single score/confidence value into calibrated, horizon-specific outcome probabilities and risk distributions for 1, 2, 3, 5 and 7 trading days.

## Scope
- Produce horizon-specific probability of positive return.
- Estimate probability of reaching target within the selected horizon.
- Estimate probability of reaching stop loss within the selected horizon.
- Estimate expected return and downside distribution where evidence supports it.
- Preserve score, confidence and confidence quality as separate concepts.
- Calibrate outputs against completed historical outcomes.
- Respect EPIC-078 evidence-quality state.
- Preserve model/version metadata and point-in-time inputs.
- Add deterministic calibration and boundary tests.

## Non-goals
- Automatic trading or position execution.
- Replacing existing score/confidence without validation.
- Presenting unsupported probabilities when samples are insufficient.
- Medium/long-term modeling beyond interfaces required for future horizons.

## Acceptance Criteria
- 1/2/3/5/7-day outputs are independently measurable.
- Probability values are calibrated against historical outcomes.
- Target-hit and stop-loss probabilities are distinguishable.
- Insufficient evidence/sample states are explicit.
- Outputs are reproducible and auditable.
- Existing recommendation contracts remain authoritative.

## Dependency Chain
**Previous:** EPIC-078 Evidence Completeness & Point-in-Time Data Quality + EPIC-072 Recommendation Confidence Analysis + EPIC-042 Target & Stop-Loss Engine.
**Next:** EPIC-076 Generic Stock Analysis.

## Execution Rule
Never present a probability as calibrated when evidence or sample size is insufficient. Existing score and confidence must remain backward compatible.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-079

### Branch

autonomous/epic-m1-75, branched cleanly from `main` (the declared dependencies -- EPIC-078, EPIC-072, EPIC-042 -- are already merged).

### Objective

Extend short-term recommendation outputs from a single score/confidence value into calibrated, horizon-specific outcome probabilities and risk distributions for 1, 2, 3, 5 and 7 trading days.

### Design

`SUPPORTED_HORIZON_DAYS = (1, 2, 3, 5, 7)` is this EPIC's own named interface contract, deliberately including day 2 even though `app.recommendations.VALID_HORIZON_DAYS = (1, 3, 5, 7)` never actually produces a `Prediction` with `horizon_days == 2` today -- the same honest, forward-compatible posture EPIC-041 already established for its never-yet-populated MEDIUM/LONG horizon bands (`test_day_two_is_always_insufficient_sample` proves day 2 always reports zero real evidence, never a fabricated number). A `HorizonProbabilityProfile` is a property of one `(model_version, horizon_days)` cohort, not of a single prediction -- the same "one check row per cohort, append-only" shape EPIC-062's `ModelRegressionCheck` already established, reused here for a calibrated distribution rather than a regression verdict.

### Respecting EPIC-078's Evidence-Quality State

The calibration sample is filtered to only historical predictions whose latest EPIC-078 `EvidenceQualityDecision` was `STATE_SUFFICIENT` -- a prediction never gated, or gated `INSUFFICIENT`/`LEAKAGE_DETECTED`, cannot quietly influence a probability someone else will rely on (`test_ungated_and_insufficiently_gated_predictions_are_excluded`).

### Distinguishable Probabilities And Downside Distribution

`positive_return_probability`, `target_hit_probability`, and `stop_hit_probability` are computed and stored as three independent fields (AC: "target-hit and stop-loss probabilities are distinguishable"); `expected_return` (mean) and `downside_p10_return` (a fixed, documented 10th-percentile, linear-interpolation calculation) together satisfy "estimate expected return and downside distribution where evidence supports it" -- `test_calibrated_profile_has_correct_probabilities` proves all five numbers against a hand-computed expectation.

### Existing Contracts Remain Authoritative

This module never reads or writes `Prediction.opportunity_score`/`confidence`; `HorizonProbabilityProfile` is an entirely new, additive table, and `get_probability_profile_for_prediction` is a pure read that attaches the latest cohort profile without ever mutating the prediction (`test_computation_never_writes_to_prediction`).

### Reproducible And Auditable

Deterministic given the same underlying, already-immutable evidence; append-only, so a later `compute_horizon_probability_profile` call for the same cohort is a genuinely new, independent row, never a mutation of a prior one (`test_profile_history_and_latest`).

### Files Changed

- `app/short_horizon_probability.py` — new: `compute_horizon_probability_profile`, `get_latest_probability_profile`, `get_probability_profile_for_prediction`, `get_profile_history`, constants.
- `app/models.py` — new `HorizonProbabilityProfile` model.
- `migrations/versions/0056_horizon_probability.py` — new migration.
- `tests/test_short_horizon_probability.py` — new: 7 tests.
- `docs/epics/EPIC-079-short-horizon-probability-outcome-distribution.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_short_horizon_probability.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0056_horizon_probability`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0055` through `0056` (verified `horizon_probability_profiles` created), `downgrade -1` (verified dropped), `upgrade head` again (clean re-apply).

### Test Results

- `pytest -q`: **665 passed, 0 failed**.
- `test_short_horizon_probability.py`: **7 passed** — day 2 always reports insufficient sample; below-minimum raw sample is insufficient; a calibrated profile's five numbers (positive-return, target-hit, stop-hit probability, expected return, 10th-percentile downside) exactly match a hand-computed expectation over a known win/loss mix; predictions never gated or gated insufficient by EPIC-078 are correctly excluded from the sample; profile history and "latest" lookups behave correctly across repeated computations; a profile correctly attaches to a prediction sharing its `(model_version, horizon_days)` cohort; computation never writes to `Prediction`.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] 1/2/3/5/7-day outputs are independently measurable (`horizon_days` is part of every profile's identity; day 2 honestly reports no evidence).
- [x] Probability values are calibrated against historical outcomes (real `PredictionOutcome` rows, EPIC-078-filtered).
- [x] Target-hit and stop-loss probabilities are distinguishable (three independent fields).
- [x] Insufficient evidence/sample states are explicit (`VERDICT_INSUFFICIENT_SAMPLE`, all probability fields `None`).
- [x] Outputs are reproducible and auditable (deterministic, immutable, append-only).
- [x] Existing recommendation contracts remain authoritative (no read/write of `Prediction.opportunity_score`/`confidence`; proven by test).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip and a hand-verified exact match of every calibrated probability and distribution figure. One incidental observation surfaced while writing tests, noted for future awareness rather than fixed here (out of this EPIC's scope): EPIC-030's `check_market_data_freshness` takes the globally-latest `MarketPrice` row for a stock rather than filtering to `timestamp <= as_of_timestamp`, so capturing an EPIC-043 evidence snapshot *after* a later price bar already exists for that stock will correctly (if perhaps surprisingly) trigger this EPIC's own leakage detector; production code that captures evidence at decision time, before any future price data exists, is unaffected. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
