# EPIC-023 — Discovery Effectiveness Learning

**Status:** DONE  
**Execution Status:** COMPLETED  
**Priority:** P1

## Objective
Measure which discovery sources and candidate characteristics actually produce successful recommendations.

## Scope
- Record discovery basis for every candidate: universe, market-cap, sector, industry, technical/event trigger, user watchlist, or external discovery.
- Track candidate → recommendation → outcome conversion.
- Measure discovery success by source, segment, and horizon.
- Identify high- and low-performing discovery paths.
- Preserve discovery provenance permanently.

## Non-goals
- Automatically changing discovery rules.
- LLM-controlled recommendations.
- Trading automation.

## Acceptance Criteria
- Every candidate has traceable discovery provenance.
- Discovery effectiveness is measurable after outcomes close.
- Metrics distinguish candidate rejection from recommendation failure.
- Results are segmented by market regime and horizon where available.
- Historical provenance cannot be overwritten.

## Dependency Chain
**Previous:** EPIC-020, EPIC-070, EPIC-021, EPIC-022  
**Next:** EPIC-025, EPIC-027

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-023

### Branch

autonomous/epic-m1-28, branched cleanly from `main` (all four declared dependencies -- EPIC-020, EPIC-070, EPIC-021, EPIC-022 -- are already merged).

### Objective

Measure which discovery sources actually produce successful recommendations, tracking the full candidate → recommendation → outcome funnel per source, without ever conflating a consensus rejection with a realized recommendation failure.

### Design Decisions

- **Closed a real, pre-existing gap this EPIC's own AC required:** `DiscoveryRecord` (EPIC-020) had no immutability guard at all. Added one in `app/discovery.py` protecting the true provenance fields (`scan_id`, `stock_id`, `source`, `rationale`, `discovered_at`, `created_at`) -- but **deliberately excluding** `recommendation_generation_id`, which starts `None` and is legitimately set exactly once, later, by `route_discovery_through_pipeline`'s own real `UPDATE`. That is a forward link populated by routing, not provenance itself; guarding it would have broken EPIC-020/EPIC-068/EPIC-028's existing, already-tested linking behavior. Proven safe by two new tests: one confirming provenance fields raise `DiscoveryRecordImmutableError`, one confirming the one-time link-population still works.
- **No new table or migration** otherwise -- `app/discovery_effectiveness.py` is pure read-side aggregation, outer-joining `DiscoveryRecord` → `RecommendationGeneration` → `Prediction` → `PredictionOutcome`, plus `MarketRegime` (EPIC-021) via `scan_id`.
- **The funnel is the literal point of this EPIC, distinguishing every stage**: `discovered_count` (a `DiscoveryRecord` exists) → `routed_count` (a `RecommendationGeneration` was produced) → `rejected_count` (`NOT_QUALIFIED`, a **candidate rejection**) vs. `qualified_count` (`QUALIFIED`) → among qualified, `open_count`/`unevaluable_count`/`success_count`/`failure_count` (a **recommendation failure** is only ever counted here, never in `rejected_count`) — proven directly by `test_rejection_and_failure_are_never_conflated`.
- **"Identify high- and low-performing discovery paths" reuses EPIC-019's exact `WEAK`/`OK`/`INSUFFICIENT_SAMPLE` policy** (`MIN_SAMPLE_SIZE_FOR_COMPARISON`, `WEAKNESS_MARGIN`, imported not redefined) comparing each source's success rate against the global rate across all sources -- the same established "is this segment's evidence reliable, and is it underperforming" question this platform already answers consistently everywhere else (EPIC-019/EPIC-071/EPIC-072/EPIC-074/EPIC-022).
- **Horizon segmentation is fully covered** (every qualified, evaluated `Prediction` has a `horizon_days`). **Market-regime segmentation is reported only where available** -- a `MarketRegime` row exists only for scans explicitly classified (EPIC-021) -- matching scope item 3's own "where available" qualifier and this platform's established honest-partial-coverage pattern (EPIC-072/EPIC-074/EPIC-022).

### Files Changed

- `app/discovery_effectiveness.py` — new: `compute_discovery_effectiveness_report`, `DiscoverySourceFunnel`, `SourceHorizonMetric`, `SourceRegimeMetric`.
- `app/discovery.py` — added `DiscoveryRecordImmutableError` and a `before_update` guard on `DiscoveryRecord`'s provenance fields (no change to existing EPIC-020 function behavior).
- `tests/test_discovery.py` — added 2 tests for the new immutability guard.
- `tests/test_discovery_effectiveness.py` — new: 7 tests.
- `docs/epics/EPIC-023-discovery-effectiveness-learning.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_discovery_effectiveness.py tests/test_discovery.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (no migration added by this EPIC; head unchanged from EPIC-021's `0021_market_regimes`)

### Test Results

- `pytest -q`: **262 passed, 0 failed** (253 pre-existing from `main` + 2 new in `test_discovery.py` + 7 new in `test_discovery_effectiveness.py`).
- `pytest -v tests/test_discovery_effectiveness.py`: **7 passed** — a discovered-but-not-yet-routed candidate is counted in `discovered_count` only; a rejected candidate and a separately qualified-but-failed one are correctly counted in `rejected_count` and `failure_count` respectively, never conflated; an open (no outcome yet) and an unevaluable (bad data) candidate are counted separately from success/failure; a 20-sample 100%-success source is `OK` while a 20-sample 0%-success source is `WEAK` against the same overall rate; a 3-sample source with a real gap is `INSUFFICIENT_SAMPLE`, not `WEAK`; regime segmentation includes only a scan that was actually classified; and horizon segmentation correctly isolates a horizon-1 recommendation.
- `pytest -v tests/test_discovery.py`: **10 passed** (8 pre-existing + 2 new) — a direct mutation of `rationale` after creation raises `DiscoveryRecordImmutableError`; routing's one-time `None -> generation.id` link-population continues to work unaffected by the new guard.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: unchanged, single head `0021_market_regimes` (no migration in this EPIC).

### Acceptance Criteria

- [x] Every candidate has traceable discovery provenance (every row starts from a `DiscoveryRecord`).
- [x] Discovery effectiveness is measurable after outcomes close (`success_rate` computed only from closed `SUCCESS`/`FAILURE` outcomes).
- [x] Metrics distinguish candidate rejection from recommendation failure (proven directly by test).
- [x] Results are segmented by market regime and horizon where available.
- [x] Historical provenance cannot be overwritten (new `DiscoveryRecordImmutableError` guard, proven by test).

### Claude Assessment

I believe this implementation satisfies all five acceptance criteria with real, verified evidence. Closing the pre-existing `DiscoveryRecord` immutability gap -- rather than working around it or ignoring that AC -- required a small, carefully-scoped, additive change to an already-merged EPIC's file; I verified it doesn't alter any existing behavior via the existing full discovery-related test suite plus two new targeted tests. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->
