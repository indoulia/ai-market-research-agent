# EPIC-022 — Sector & Market-Cap Performance Learning

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1

## Objective
Measure recommendation performance across sector, industry, market-cap, liquidity, and horizon segments.

## Scope
- Persist stable sector/industry/market-cap/liquidity classifications at recommendation time.
- Calculate success rate and realized return by segment and horizon.
- Require minimum sample counts before reporting conclusions.
- Preserve historical classifications; do not rewrite old recommendations.
- Produce machine-readable metrics for later calibration.

## Non-goals
- Changing scores.
- Recommending sectors automatically.
- Portfolio allocation.

## Acceptance Criteria
- Segment metrics are reproducible.
- Historical recommendations retain their original segment context.
- Small samples are explicitly marked insufficient.
- Metrics are separated by 1/3/5/7-day horizon.
- No future information leaks into segment attribution.

## Dependency Chain
**Previous:** EPIC-019, EPIC-070, EPIC-021  
**Next:** EPIC-024, EPIC-025

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-022

### Branch

autonomous/epic-m1-27, branched cleanly from `main` (all three declared dependencies -- EPIC-019, EPIC-070, EPIC-021 -- are already merged).

### Objective

Measure recommendation success rate and realized return across sector/industry/market-cap/liquidity segments, further split by horizon, without rewriting any historical classification or score.

### Design Decisions

- **No new table or migration.** "Persist stable classifications at recommendation time" (scope item 1) is already fully satisfied by EPIC-029's `DiscoverySegment` -- an immutable, discovery-time snapshot with its own `before_update` guard. This EPIC adds no new classification logic; it is pure read-side aggregation joining `Prediction`/`PredictionOutcome` to `DiscoverySegment` via `RecommendationGeneration`/`DiscoveryRecord`.
- **`DiscoverySegment` coverage is not universal** -- only candidates explicitly segmented (via `record_segments_for_scan`) have one. This module doesn't force universal coverage (that would mean modifying `app/continuous_discovery.py`'s already-merged orchestration, out of scope here); a segment with zero or few samples is reported with an explicit `INSUFFICIENT_SAMPLE` verdict, honestly reflecting current coverage. Documented for reviewer scrutiny, same rationale as EPIC-072/EPIC-074's deferred-segmentation notes.
- **Open-vocabulary dimensions are reported by observation, not exhaustively enumerated.** Unlike EPIC-006's ten fixed probability buckets, `sector`/`industry` are open strings with no fixed universe to enumerate -- this report lists only segment/horizon combinations that actually occurred, rather than a fixed grid padded with empty entries.
- **Reuses EPIC-019's `MIN_SAMPLE_SIZE_FOR_COMPARISON`** (not a new threshold) for the insufficient-sample gate (scope item 3), consistent with every other segment-reliability question this platform already answers the same way (EPIC-071/EPIC-072/EPIC-074).
- **A prediction contributes to a segment/horizon bucket at most once per distinct value it holds**, even if it has multiple `DiscoverySegment` rows (e.g. discovered via more than one source and segmented each time) -- deduplicated by `(dimension, key)` per prediction, so a single recommendation can never be double-counted within the same segment value.
- **Metrics are segmented by horizon independently** (scope item 4, "metrics are separated by 1/3/5/7-day horizon"): the same segment key at different horizons is a genuinely separate bucket with its own sample count and verdict, proven directly by a test.
- **"No future information leaks into segment attribution" (AC)** holds by construction: only already-evaluated (`SUCCESS`/`FAILURE`) outcomes are queried; open/unevaluable recommendations contribute nothing.
- **"Historical recommendations retain their original segment context" (AC)** is proven directly: reclassifying a `Stock.sector` after the fact does not change the historical metric, since `DiscoverySegment` is immutable and the report re-derives from that snapshot, not from `Stock`'s current fields.

### Files Changed

- `app/segment_performance.py` — new: `compute_segment_performance_report`, `SegmentMetric`, `SegmentPerformanceReport`, dimension constants.
- `tests/test_segment_performance.py` — new: 5 tests.
- `docs/epics/EPIC-022-sector-market-cap-performance-learning.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_segment_performance.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (no migration added by this EPIC; head unchanged from EPIC-021's `0021_market_regimes`)

### Test Results

- `pytest -q`: **253 passed, 0 failed** (248 pre-existing from `main` + 5 new).
- `pytest -v tests/test_segment_performance.py`: **5 passed** — empty history reports zero metrics rather than fabricated ones; a sector with 5 samples is `INSUFFICIENT_SAMPLE`; a sector with 20 samples reports a correct 50% success rate, `OK` verdict, and a non-null average actual return; the identical sector at two different horizons (20 samples at horizon 1, 5 at horizon 3) shows independent, correctly-differentiated verdicts and sample counts; and reclassifying a stock's `sector` after the fact leaves the historical metric's sample count and content unchanged.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: unchanged, single head `0021_market_regimes` (no migration in this EPIC).

### Acceptance Criteria

- [x] Segment metrics are reproducible (plain deterministic aggregation).
- [x] Historical recommendations retain their original segment context (proven by the reclassification test).
- [x] Small samples are explicitly marked insufficient (`VERDICT_INSUFFICIENT_SAMPLE`).
- [x] Metrics are separated by 1/3/5/7-day horizon (proven by the horizon-independence test).
- [x] No future information leaks into segment attribution (only closed `SUCCESS`/`FAILURE` outcomes queried).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence. The central scope decision -- reporting observed segment/horizon combinations only, and being explicit about `DiscoverySegment`'s partial coverage rather than forcing universal coverage out of this EPIC's scope -- is documented above for reviewer scrutiny. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
