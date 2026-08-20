# EPIC-M1.11 — Recommendation Calibration Feedback Loop

**Status:** APPROVED  
**Execution Status:** READY_FOR_EXECUTION  
**Approved By:** ChatGPT  
**Priority:** P1

## Objective

Use completed recommendation outcomes to measure and improve probability calibration without changing the underlying prediction model in this EPIC.

## Why now

M1.5 and M1.6 create the objective outcome history needed to determine whether stated probabilities correspond to observed success rates. This is essential before claiming that a probability such as 70% has meaningful trust value.

## Scope

1. Group completed recommendations into probability buckets.
2. Compare predicted probability with observed success rate.
3. Calculate calibration error using a documented deterministic method.
4. Report calibration by horizon where sample size is sufficient.
5. Identify materially under- or over-confident probability ranges.
6. Preserve historical predictions; do not rewrite issued probabilities.
7. Add tests against known outcome fixtures.

## Non-goals

- Automatic model retraining.
- Changing historical recommendations.
- Changing the positive-consensus criteria.
- Creating recommendations.
- LLM-based calibration.
- UI/dashboard work.

## Acceptance Criteria

- [ ] Calibration statistics are calculated only from objectively evaluated outcomes.
- [ ] Predicted probability and observed success rate are shown together.
- [ ] Sample size accompanies every calibration statistic.
- [ ] Calibration is available by supported horizon when sufficient data exists.
- [ ] Historical predictions remain immutable.
- [ ] Insufficient samples are explicitly marked rather than presented as reliable statistics.
- [ ] Tests verify calibration calculations against deterministic fixtures.

## Dependencies

- M1.5 — Evaluate Recommendation Outcomes
- M1.6 — Positive Recommendation Performance Report

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.11

### Branch

autonomous/epic-m1-11 (stacked on the still-open `autonomous/epic-m1-6` branch/PR #24, since M1.11 depends on M1.6 and it hasn't merged yet)

### Authorization note

The `origin/planning/approve-m1-8-m1-11` branch (pushed by ChatGPT, not yet merged) flips this EPIC's Status/Execution Status from `READY_FOR_APPROVAL`/`NOT_READY` to `APPROVED`/`READY_FOR_EXECUTION`, alongside M1.8–M1.10. Since this branch stacks on `autonomous/epic-m1-6` (not on that approval branch, as M1.11 depends on M1.6 rather than M1.8), the status lines above were updated directly here to match that already-issued approval rather than inheriting it via a merge.

### Objective

A deterministic calibration report (`app/calibration.py`) comparing predicted probability against observed success rate, over M1.5's objectively evaluated outcomes only, without touching any historical prediction or retraining anything.

### Design Decisions

- **`CALIBRATION_VERSION = "CAL-001"`.**
- **Reuses M1.6's exact 10 fixed probability buckets** (imports `PROBABILITY_BUCKET_COUNT`/`PROBABILITY_BUCKET_WIDTH` from `app/performance.py` so the two reports' buckets are guaranteed identical, rather than duplicating the constants and risking drift) — scope item 1.
- **Per bucket:** `predicted_probability` is the *mean* `predicted_probability` of evaluated recommendations landing in that bucket (not just the bucket's nominal range), shown alongside `observed_success_rate` and `sample_size` together (scope item 2, AC "shown together" + "sample size accompanies every statistic").
- **Calibration error** = `observed_success_rate - predicted_probability` (signed: positive means the model was underconfident — actual success exceeded what it predicted; negative means overconfident) — a plain, documented, deterministic arithmetic difference (scope item 3, no learned/statistical model).
- **`MIN_SAMPLE_SIZE = 30`**: below this, a bucket's `assessment` is `INSUFFICIENT_SAMPLE` and `calibration_error` is `None` — never a number dressed up as reliable (AC). `predicted_probability`/`observed_success_rate` are still shown even when insufficient, since the raw counts are honest data; only the *error/assessment* judgment is withheld.
- **`MATERIAL_ERROR_THRESHOLD = Decimal("0.10")`**: a |error| at or above this (with a sufficient sample) is flagged `OVERCONFIDENT` or `UNDERCONFIDENT`; otherwise `WELL_CALIBRATED` — scope item 5's "materially" qualifier made concrete and fixed.
- **By horizon:** the same bucket computation repeated independently for each of `VALID_HORIZON_DAYS`, including horizons with zero evaluated recommendations (reported as `INSUFFICIENT_SAMPLE` with `sample_size=0`, not omitted) — scope item 4.
- **Immutability:** this report only *reads* `Prediction`/`PredictionOutcome` rows via a plain `SELECT`; it contains no `UPDATE`/`INSERT` at all, so historical predictions are structurally impossible for it to rewrite (scope item 6, AC).
- Deliberately did **not** modify `app/performance.py` (M1.6, already implemented/PR'd) to avoid retroactively changing a completed, separately-reviewed EPIC — this module duplicates only its own bucketing index logic (`_bucket_index`, ~2 lines) since M1.6's equivalent helper is private to that module.

### Files Changed

- `app/calibration.py` — new: calibration report, bucketing, and assessment logic.
- `tests/test_recommendation_calibration.py` — new: 8 tests.
- `docs/epics/EPIC-M1.11-calibration-feedback-loop.md` — status update to match the already-issued approval, plus this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m pytest -v tests/test_recommendation_calibration.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`

### Test Results

- `pytest -q`: **51 passed**, 4.74s (43 pre-existing/M1.6 + 8 new).
- `pytest -v tests/test_recommendation_calibration.py`: **8 passed** — covers an insufficient-sample bucket (5 evaluated, explicitly marked, no error computed, but predicted/observed still shown), a well-calibrated bucket (40 samples, exact match), an overconfident bucket (40 samples, observed 30 points below predicted), an underconfident bucket (40 samples, observed 30 points above predicted), open/unevaluable rows confirmed excluded from sample size and rate, a per-horizon breakdown across all 4 supported horizons (one well-calibrated, one insufficient-sample, one zero-sample — all three states represented), determinism/repeatability, and that computing the report never modifies the underlying `Prediction` row.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Caught and fixed two test-authoring mistakes during development (not production bugs): `evaluate_recommendation` returns the `PredictionOutcome`, not the `Prediction` — an immutability test had captured the wrong object; and an early by-horizon fixture used a 100%-success sample against a 70%-predicted bucket, which is genuinely underconfident, not well-calibrated as the test had assumed — corrected the fixture's success/failure mix to match the intended assertion.

### Acceptance Criteria

- [x] Calibration statistics are calculated only from objectively evaluated outcomes.
- [x] Predicted probability and observed success rate are shown together.
- [x] Sample size accompanies every calibration statistic.
- [x] Calibration is available by supported horizon when sufficient data exists.
- [x] Historical predictions remain immutable (report is read-only by construction).
- [x] Insufficient samples are explicitly marked rather than presented as reliable statistics.
- [x] Tests verify calibration calculations against deterministic fixtures.

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence, including catching two of my own test-authoring mistakes during development (documented above) before they could produce a false sense of correctness. The specific `MIN_SAMPLE_SIZE`/`MATERIAL_ERROR_THRESHOLD` values are a design decision within the EPIC's deliberately open scope, documented above for reviewer scrutiny. This is NOT final approval — that remains the reviewer's call, and per the corrected contract, Claude will not merge this PR.

## Review History

<!-- ChatGPT: append review decisions here. Do not delete prior reviews. -->
