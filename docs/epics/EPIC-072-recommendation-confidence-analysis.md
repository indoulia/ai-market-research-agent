# EPIC-072 — Recommendation Confidence Analysis

**Status:** DONE  
**Execution Status:** COMPLETED  
**Approved By:** User  
**Priority:** P1

## Objective
Measure whether reported prediction probabilities and confidence levels correspond to realized recommendation outcomes across horizons and evidence segments.

## Scope
1. Compare predicted probabilities with observed success rates.
2. Measure calibration by horizon and probability/confidence bucket.
3. Identify persistent over-confidence and under-confidence.
4. Report calibration error and sample sizes.
5. Segment confidence behavior by regime/sector/market-cap when sufficient evidence exists.
6. Produce deterministic, versioned analysis artifacts.
7. Preserve original issued confidence values.

## Non-goals
- Automatic confidence changes.
- Production model replacement.
- Rewriting historical recommendations.
- Trading decisions.

## Acceptance Criteria
- [ ] Calibration metrics are reproducible.
- [ ] Every confidence/probability metric includes sample count.
- [ ] Insufficient samples are explicit.
- [ ] Over-confidence and under-confidence can be identified objectively.
- [ ] Historical confidence remains immutable.
- [ ] Tests validate known calibration fixtures.

## Dependency Chain
### Previous / Required
- **EPIC-071 — Recommendation Score Analysis**
- **EPIC-019 — Recommendation Trust Report**

### Next / Unlocks
- **EPIC-073 — Historical Recommendation Replay**

### Chain Position
`EPIC-067 → EPIC-068 → EPIC-069 → EPIC-070 → EPIC-071 → EPIC-072 → EPIC-073 → EPIC-074`

## Execution Rule
Confidence analysis must remain observational. Any calibration change must be versioned and separately validated before production use.

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-072

### Branch

autonomous/epic-m1-23, branched cleanly from `main` (both declared dependencies, EPIC-071 and EPIC-019, are already merged).

### Objective

Measure whether EPIC-016's reported `predicted_probability` corresponds to realized EPIC-005 outcomes -- true calibration -- across horizons, without ever rewriting a historical confidence value.

### Design Decisions

- **No new table or migration.** Read-only aggregation over `Prediction`/`PredictionOutcome`, exactly like EPIC-006/EPIC-019/EPIC-071.
- **Genuine calibration, distinct from EPIC-019's weak-segment detection.** EPIC-019 flags a bucket performing *below the platform's overall success rate*; this EPIC instead compares each bucket's *own* average stated `predicted_probability` against its *own* observed success rate (`calibration_error = average_predicted - observed`) -- the actual definition of calibration, and a materially different question from EPIC-019's. Reuses EPIC-006's ten fixed-width probability buckets (`PROBABILITY_BUCKET_COUNT`/`PROBABILITY_BUCKET_WIDTH`, both public) rather than redefining bucket boundaries a third time.
- **`CALIBRATION_ERROR_MARGIN = Decimal("0.10")`** (fixed, documented, versioned via `CONFIDENCE_ANALYSIS_VERSION`): a signed gap at or beyond this margin is `OVERCONFIDENT` (stated probability higher than reality) or `UNDERCONFIDENT` (lower); within the margin is `WELL_CALIBRATED`.
- **"Persistent" over/under-confidence (scope item 3)** is interpreted as "a gap that clears the same minimum-sample floor EPIC-019 already uses" (`MIN_SAMPLE_SIZE_FOR_COMPARISON`, reused, not redefined) -- a large gap on a handful of samples is noise, not a persistent pattern, so it's reported as `INSUFFICIENT_SAMPLE` instead of a fabricated verdict. This interpretation is a documented judgment call, since the EPIC doesn't define "persistent" precisely.
- **Segmenting by market regime/sector/market-cap (scope item 5) was deliberately scoped down to horizon only.** Market regime doesn't exist yet (EPIC-021 is blocked pending the still-missing EPIC-067-25-adjacent EPICs it itself depends on being fully executed, and regardless regime detection isn't implemented). Sector/market-cap classifications exist via EPIC-029's `DiscoverySegment`, but that table is only populated for candidates that went through `record_segments_for_scan`, not universally for every `Prediction` -- joining on it today would silently under-represent most historical recommendations rather than reporting real, complete evidence. Per this platform's standing rule against fabricating or half-covering analysis, this EPIC reports horizon segmentation (scope item 2, fully data-backed for every recommendation) and leaves regime/sector/market-cap segmentation for a future EPIC once that underlying data is universally available. Documented here for reviewer scrutiny.
- **"Preserve original issued confidence values" (scope item 7)** holds trivially: no write path exists in this module.

### Files Changed

- `app/confidence_analysis.py` — new: `compute_confidence_analysis_report`, `ProbabilityBucketCalibration`, `HorizonCalibration`, `ConfidenceAnalysisReport`.
- `tests/test_confidence_analysis.py` — new: 6 tests.
- `docs/epics/EPIC-072-recommendation-confidence-analysis.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_confidence_analysis.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (no migration added by this EPIC; head unchanged from EPIC-069's `0019_watchlist_decisions`)

### Test Results

- `pytest -q`: **228 passed, 0 failed** (222 pre-existing from `main` + 6 new).
- `pytest -v tests/test_confidence_analysis.py`: **6 passed**, each against a known calibration fixture (AC: "tests validate known calibration fixtures") — empty history is `INSUFFICIENT_SAMPLE` everywhere; a bucket predicting `0.75` where exactly 15/20 (75%) succeed shows `calibration_error == 0` and `WELL_CALIBRATED`; a bucket predicting `0.95` where only 4/20 (20%) succeed shows a large positive error and `OVERCONFIDENT`; a bucket predicting `0.65` where 19/20 (95%) succeed shows a large negative error and `UNDERCONFIDENT`; the identical large gap on only 5 samples is `INSUFFICIENT_SAMPLE`, not flagged; and the by-horizon breakdown always reports all four supported horizons.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: unchanged, single head `0019_watchlist_decisions` (no migration in this EPIC).

### Acceptance Criteria

- [x] Calibration metrics are reproducible (plain deterministic aggregation).
- [x] Every confidence/probability metric includes sample count (`evaluated_count` per bucket).
- [x] Insufficient samples are explicit (`VERDICT_INSUFFICIENT_SAMPLE`).
- [x] Over-confidence and under-confidence can be identified objectively (`calibration_error` sign/magnitude against a fixed margin).
- [x] Historical confidence remains immutable (no write path in this module).
- [x] Tests validate known calibration fixtures.

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence. Two scope items required genuine judgment, both documented above: interpreting "persistent" as sample-floor-gated, and deliberately not attempting regime/sector/market-cap segmentation given incomplete underlying data rather than reporting misleadingly partial coverage. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
