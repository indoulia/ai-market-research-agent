# EPIC-006 — Positive Recommendation Performance Report

**Status:** DONE
**Priority:** P1

## Objective

Measure the historical performance of positive recommendations using only objectively evaluated outcomes.

## Dependencies

- EPIC-005 — Evaluate Recommendation Outcomes

## Scope

1. Calculate overall positive-recommendation success rate.
2. Calculate success by 1/3/5/7-day horizon.
3. Report predicted versus actual return.
4. Report average winning and losing return.
5. Report performance by probability/confidence bucket.
6. Always expose the sample size with percentages.
7. Keep failed recommendations visible; do not cherry-pick successes.

## Acceptance Criteria

- [ ] Overall success rate is calculated from evaluated recommendations only.
- [ ] Horizon-specific success rates are available.
- [ ] Predicted versus actual return statistics are available.
- [ ] Probability/confidence bucket performance is available.
- [ ] Every percentage includes its underlying sample count.
- [ ] Unevaluable recommendations are excluded from success-rate denominators and reported separately.
- [ ] Tests verify calculations against known fixtures.

## Non-goals

- Model retraining.
- Recommendation generation changes.
- Watchlist workflow.
- UI/dashboard work.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-006

### Branch

autonomous/epic-m1-6 (branched cleanly from `main`; only dependency is EPIC-005, already merged)

### Objective

A deterministic performance report (`app/performance.py`) over positive-recommendation outcomes already produced by EPIC-005, with no cherry-picking and every percentage carrying its sample size.

### Design Decisions

- **`REPORT_VERSION = "PERF-001"`.**
- **Population split, computed from a single `Prediction` LEFT JOIN `PredictionOutcome`:** `open` (no outcome row yet — horizon hasn't elapsed), `unevaluable` (`PredictionOutcome.outcome == "UNEVALUABLE"`), `evaluated` (`SUCCESS`/`FAILURE`). Only `evaluated` feeds the success-rate denominator (AC); `open`/`unevaluable` are still counted and exposed, never silently dropped (AC).
- **Horizon breakdown:** all four `VALID_HORIZON_DAYS` (1/3/5/7) are always reported, even with zero samples (`success_rate=None`, `evaluated_count=0`) — a horizon nothing has resolved at yet is shown as "no data," not omitted.
- **Probability buckets:** ten fixed-width `[0.0, 1.0]` buckets (`[0.0,0.1)` ... `[0.9,1.0]`), always all ten reported regardless of whether they contain data, same "no silent omission" rationale as horizons. Bucketing is on `predicted_probability` (the model's calibrated output) — "confidence" per the EPIC's "probability/confidence bucket" phrasing is treated as referring to this same field, since `Prediction.confidence` is a separate, distinct existing field with no established meaning of its own to bucket by; this is a design decision documented here for reviewer scrutiny.
- **Returns:** average predicted return (`target_return`) vs. average actual return (`actual_return`), plus average winning (`SUCCESS`) and losing (`FAILURE`) returns with their own counts — computed only over the `evaluated` population, since `UNEVALUABLE` outcomes have a placeholder `actual_return=0` (per EPIC-005) that is not a real observed return and would silently distort the average if included.
- All statistics are plain arithmetic (mean, count, ratio) over stored rows — no LLM reasoning, no learned weights, per the platform's standing constraint that quantitative evidence must be deterministic/statistical.

### Files Changed

- `app/performance.py` — new: `compute_performance_report` and all report dataclasses.
- `tests/test_positive_recommendation_performance.py` — new: 6 tests.
- `docs/epics/EPIC-006-positive-recommendation-performance.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m pytest -v tests/test_positive_recommendation_performance.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`

### Test Results

- `pytest -q`: **43 passed**, 3.52s (37 pre-existing on `main` + 6 new).
- `pytest -v tests/test_positive_recommendation_performance.py`: **6 passed** — covers an empty-history case (no fabricated rate, all `None`s), a mixed population (1 success + 1 failure + 1 unevaluable + 1 still-open, across independent stocks so evaluation windows can never cross-contaminate) verifying the overall rate excludes unevaluable/open from the denominator while still counting them, a horizon breakdown showing two populated horizons plus two explicit zero-sample horizons, a returns test against known exact-hit fixtures (target hit exactly at `0.05`, stop hit exactly at `-0.03`), a probability-bucket test verifying correct bucket placement (looked up by numeric `lower` bound, not a hardcoded label string) plus all eight other buckets explicitly zero, and a not-cherry-picked test with three independent all-failing recommendations.
- **Caught and fixed a test-methodology bug during development, not a bug in `app/performance.py` itself:** several early drafts of the multi-recommendation tests reused the same stock across recommendations with different price-window start offsets, all sharing the same `as_of_timestamp`. Since `evaluate_recommendation` (EPIC-005) selects the earliest `horizon_days` price rows after `as_of_timestamp` for a given stock, later recommendations' evaluation windows silently picked up earlier recommendations' price rows instead of their own. Fixed by giving every recommendation in a multi-recommendation test its own stock, eliminating any possibility of window overlap.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).

### Acceptance Criteria

- [x] Overall success rate is calculated from evaluated recommendations only.
- [x] Horizon-specific success rates are available.
- [x] Predicted versus actual return statistics are available.
- [x] Probability/confidence bucket performance is available.
- [x] Every percentage includes its underlying sample count.
- [x] Unevaluable recommendations are excluded from success-rate denominators and reported separately.
- [x] Tests verify calculations against known fixtures.

### Claude Assessment

I believe this implementation satisfies all seven acceptance criteria with real, verified evidence, including catching and fixing a genuine test-isolation bug during development (documented above) that would otherwise have silently produced misleading results. The choice to bucket by `predicted_probability` rather than `confidence` is a design decision within the EPIC's ambiguous "probability/confidence bucket" phrasing, documented above for reviewer scrutiny. This is NOT final approval — that remains the reviewer's call, and per the corrected contract, Claude will not merge this PR.

## Review History

<!-- ChatGPT: append review decisions here. Do not delete prior reviews. -->
