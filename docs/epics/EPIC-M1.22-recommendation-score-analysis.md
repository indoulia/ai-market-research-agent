# EPIC-M1.22 — Recommendation Score Analysis

**Status:** APPROVED  
**Execution Status:** VALIDATING  
**Approved By:** User  
**Priority:** P1

## Objective
Measure whether the recommendation score is predictive of realized outcomes and establish evidence that later score-adjustment work can safely consume.

## Scope
1. Analyze score distributions against completed outcomes.
2. Measure success and return by score band.
3. Measure score behavior by supported horizon.
4. Preserve sample counts and unevaluable cases.
5. Identify statistically weak or insufficient score bands.
6. Produce deterministic, versioned analysis output.
7. Do not modify production scores.

## Non-goals
- Automatic score adjustment.
- Model promotion.
- Retrospective mutation of recommendations.
- Trading decisions.

## Acceptance Criteria
- [ ] Score-band performance is reproducible.
- [ ] Sample counts accompany every metric.
- [ ] Insufficient samples are explicitly identified.
- [ ] Failures and unevaluable outcomes remain visible.
- [ ] Analysis is segmented by horizon where applicable.
- [ ] No production score is changed by this EPIC.

## Dependency Chain
### Previous / Required
- **M1.21 — Recommendation Outcome Closure**
- **M1.9 — Positive Opportunity Scoring**

### Next / Unlocks
- **M1.23 — Recommendation Confidence Analysis**

### Chain Position
`M1.18 → M1.19 → M1.20 → M1.21 → M1.22 → M1.23 → M1.24 → M1.25`

## Execution Rule
This EPIC produces evidence only. Any score adjustment requires a separately approved downstream EPIC and sufficient out-of-sample evidence.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.22

### Branch

autonomous/epic-m1-22, branched cleanly from `main` (both declared dependencies, M1.21 and M1.9, are already merged).

### Objective

Measure whether M1.9's opportunity score is predictive of realized outcomes, producing deterministic, versioned, read-only evidence a later score-adjustment EPIC could consume -- without modifying any production score.

### Design Decisions

- **No new table or migration.** Exactly like M1.6 and M1.16, this is pure read-side aggregation over existing `Prediction`/`PredictionOutcome` rows.
- **New module `app/score_analysis.py`, `compute_score_analysis_report(session) -> ScoreAnalysisReport`.** Ten fixed-width bands over the `opportunity_score` `[0, 100]` range (mirroring M1.6's ten probability buckets exactly), always all ten reported even empty (scope item 1-2, "no band silently omitted").
- **Reuses M1.16's weak/insufficient-sample verdict policy wholesale** (`MIN_SAMPLE_SIZE_FOR_COMPARISON`, `WEAKNESS_MARGIN`, `VERDICT_OK`/`VERDICT_WEAK`/`VERDICT_INSUFFICIENT_SAMPLE`, imported from `app.trust_report`) rather than inventing a second, independently-tunable threshold for the same underlying question ("is this segment's sample reliable evidence?") -- score bands are just another segment dimension alongside M1.16's horizons and probability buckets. A local `_verdict` function duplicates M1.16's five-line policy check (that private helper isn't imported across modules) but the actual policy *constants* are shared, so a future threshold change updates both reports consistently.
- **"Measure score behavior by supported horizon" (scope item 3) is a genuine cross-tabulation**, not just M1.6's existing horizon breakdown: `by_horizon` computes the full ten-band breakdown independently *within* each of the four `VALID_HORIZON_DAYS`, so a score band's predictiveness can be compared across horizons, not just scores overall vs. horizons overall.
- **Re-queries `Prediction`/`PredictionOutcome` directly** (the same `LEFT JOIN` shape `app/performance.py`'s `compute_performance_report` already uses) rather than trying to extract `compute_performance_report`'s internal `evaluated` list, since that function only returns the final aggregated report, not the raw pairs a new bucketing dimension needs. This is an intentional, documented parallel structure, not a modification of M1.6's file.
- **"Do not modify production scores" (scope item 7)** holds trivially: this module contains no write path to `Prediction`, `PredictionOutcome`, or any other table.

### Files Changed

- `app/score_analysis.py` — new: `compute_score_analysis_report`, `ScoreBandPerformance`, `ScoreBandTrust`, `HorizonScoreBreakdown`, `ScoreAnalysisReport`.
- `tests/test_score_analysis.py` — new: 6 tests.
- `docs/epics/EPIC-M1.22-recommendation-score-analysis.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_score_analysis.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (no migration added by this EPIC; head unchanged from M1.20's `0019_watchlist_decisions`)

### Test Results

- `pytest -q`: **222 passed, 0 failed** (216 pre-existing from `main` + 6 new).
- `pytest -v tests/test_score_analysis.py`: **6 passed** — empty history reports `INSUFFICIENT_SAMPLE` everywhere rather than a fabricated verdict; open/unevaluable recommendations are counted but correctly excluded from the success-rate denominator; band boundaries are exact (a score of exactly `50.00` lands in `[50, 60)`, not `[40, 50)`); a band with real signal but under the 20-sample floor is `INSUFFICIENT_SAMPLE`, not `WEAK`; a 20-sample 0%-success band against a 50% overall rate is correctly `WEAK` while a same-size 100%-success band is `OK`; and the by-horizon cross-tabulation shows the identical score band (`[80, 90)`) with opposite success rates at two different horizons, with all four supported horizons always present even when empty.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: unchanged, single head `0019_watchlist_decisions` (no migration in this EPIC).

### Acceptance Criteria

- [x] Score-band performance is reproducible (plain deterministic aggregation).
- [x] Sample counts accompany every metric (`evaluated_count` on every band).
- [x] Insufficient samples are explicitly identified (`VERDICT_INSUFFICIENT_SAMPLE`).
- [x] Failures and unevaluable outcomes remain visible (`unevaluable_count`, `failure_count` per band, never filtered out).
- [x] Analysis is segmented by horizon where applicable (`by_horizon`, full cross-tabulation).
- [x] No production score is changed by this EPIC (no write path exists in this module).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence. Reusing M1.16's verdict policy constants rather than introducing a second set was a deliberate consistency choice, documented above for reviewer scrutiny. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
