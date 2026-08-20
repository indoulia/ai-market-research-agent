# EPIC-M1.42 — Discovery Effectiveness Measurement

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Measure whether each discovery source and segment actually produces useful positive recommendations and successful outcomes.

## Scope
- Track candidates by discovery source.
- Measure qualification rate.
- Measure recommendation rate.
- Measure completed success rate.
- Measure return by source and segment.
- Compare discovery channels over common periods.
- Identify weak or redundant discovery sources.

## Acceptance Criteria
- [ ] Every candidate has a discovery source.
- [ ] Discovery-to-recommendation funnel metrics are reproducible.
- [ ] Discovery-to-success metrics are calculated only from completed outcomes.
- [ ] Metrics are segmented by market, sector, size, and industry where applicable.
- [ ] Small samples are explicitly marked insufficient.
- [ ] Discovery sources can be ranked objectively.

## Dependencies
**Previous:** M1.28, M1.38, M1.39
**Next:** M1.43

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.42

### Branch

autonomous/epic-m1-42, branched cleanly from `main` (all three declared dependencies -- M1.28, M1.38, M1.39 -- are already merged).

### Objective

Measure whether each discovery source and segment actually produces useful positive recommendations and successful outcomes, comparing sources fairly over the same time period and adding return magnitude and structural redundancy measures that M1.28's funnel did not cover.

### Funnel Definitions

`discovered_count` (a `DiscoveryRecord` exists) → `routed_count` (a `RecommendationGeneration` was produced) → `rejected_count` (`NOT_QUALIFIED`, a **candidate rejection**, never conflated with a later recommendation failure) vs. `qualified_count` (`QUALIFIED`) → among qualified, `evaluated_count`/`success_count`/`failure_count` once M1.38 has actually classified the outcome. Qualification rate is `qualified_count / routed_count`; recommendation rate is `qualified_count / discovered_count` -- both directly derivable from the funnel, never a separate metric requiring new state.

### Sample-Size Rules

Every success-rate verdict (`OK`/`WEAK`/`INSUFFICIENT_SAMPLE`, M1.28's own vocabulary, reused unchanged) and every redundancy verdict (`REDUNDANT`/`NOT_REDUNDANT`/`INSUFFICIENT_SAMPLE`, this EPIC's own) requires `MIN_SAMPLE_SIZE_FOR_COMPARISON` (M1.16, 20) evaluated/discovered rows before anything other than `INSUFFICIENT_SAMPLE` is possible (AC: "small samples are explicitly marked insufficient"). `rank_discovery_sources` excludes `INSUFFICIENT_SAMPLE` sources from the ranking entirely rather than placing them arbitrarily.

### Comparative Metrics

- **Common-period comparison** (scope: "compare discovery channels over common periods"): every query filters on `DiscoveryRecord.discovered_at` -- the one timestamp every candidate has regardless of whether it was ever routed or qualified -- against a caller-supplied `EvaluationWindow` (M1.25), so two sources with different lifetimes are never compared unfairly across different periods.
- **Return by source and segment** (scope, genuinely new vs. M1.28): `average_realized_return` per source and per (source, sector)/(source, market-cap-bucket)/(source, industry)/(source, regime), from M1.38's `OutcomeMeasurement.realized_return`.
- **Segmentation** (AC: "segmented by market, sector, size, and industry where applicable"): sector/market-cap-bucket/industry via M1.34's already-persisted `DiscoverySegment` (joined by its own `discovery_record_id` unique key, not reclassified), "market" interpreted as M1.26's market regime via `MarketRegime`, all reported "where available" per this platform's established honest-partial-coverage pattern -- a discovery without a `DiscoverySegment`/`MarketRegime` row simply doesn't contribute to that breakdown.
- **Redundancy** (scope: "identify weak or redundant discovery sources", genuinely new): `DiscoveryRecord` has a `(scan_id, stock_id, source)` uniqueness constraint, so the same stock discovered by more than one source on the same scan is detectable directly from that shape -- no new table. A source's `redundancy_rate` is the fraction of its own discoveries that were also independently discovered by at least one other source in the same window; `>= REDUNDANCY_THRESHOLD (0.50)` with sufficient sample is `REDUNDANT`.

### Evidence

`test_weak_source_is_identified_against_a_strong_source` builds a 20-sample 100%-success source and a 20-sample 0%-success source in the same window and proves the strong source verdicts `OK`, the weak one `WEAK`, and `rank_discovery_sources` places the strong source first. `test_redundant_sources_are_identified_by_co_discovery` builds 20 stocks each discovered independently by two sources and proves both verdict `REDUNDANT` with `redundancy_rate == 1`; `test_non_overlapping_sources_are_not_redundant` proves the same source with no overlap verdicts `NOT_REDUNDANT` with `redundancy_rate == 0`. `test_common_period_window_excludes_discoveries_outside_it` proves a discovery six months outside the window is excluded entirely.

### Design Decisions

- **Reuses rather than duplicates**: M1.28's `VERDICT_OK`/`VERDICT_WEAK`/`VERDICT_INSUFFICIENT_SAMPLE` vocabulary (imported, not redefined), M1.16's `MIN_SAMPLE_SIZE_FOR_COMPARISON`/`WEAKNESS_MARGIN`, M1.25's `EvaluationWindow`, M1.34's persisted `DiscoverySegment`, and M1.38's `OutcomeMeasurement`. No existing module is modified.
- **Does not call M1.28's `compute_discovery_effectiveness_report` directly**: that function is unwindowed (lifetime-only), and this EPIC's core new requirement is a *common-period* comparison. Reimplementing a windowed variant of the same funnel tally (rather than adding a window parameter to M1.28's already-merged, already-tested function) keeps this EPIC additive and leaves M1.28 untouched.
- **Redundancy is structural, not a judgment call**: it falls directly out of the schema's own `(scan_id, stock_id, source)` uniqueness constraint rather than any new heuristic.

### Files Changed

- `app/discovery_effectiveness_measurement.py` — new: `compute_discovery_effectiveness_measurement`, `rank_discovery_sources`, `SourceEffectivenessMetric`/`SourceSegmentMetric`/`SourceRedundancyMetric`/`DiscoveryEffectivenessMeasurementReport` dataclasses.
- `tests/test_discovery_effectiveness_measurement.py` — new: 10 tests.
- `docs/epics/EPIC-M1.42-discovery-effectiveness-measurement.md` — this completion report.

No migration: pure read-side aggregation over existing tables, matching M1.28's own precedent.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q tests/test_discovery_effectiveness_measurement.py -v`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0028_historical_learning_records`, unchanged -- confirms no migration drift)

### Test Results

- `pytest -q`: **366 passed, 0 failed** (356 pre-existing from `main` + 10 new).
- `pytest -q tests/test_discovery_effectiveness_measurement.py -v`: **10 passed** — every candidate has a traceable discovery source; the funnel distinguishes rejection from qualification; success metrics only count completed outcomes (an open recommendation contributes to `qualified_count` but not `evaluated_count`); a small sample is marked `INSUFFICIENT_SAMPLE`; a weak source is correctly identified against a strong one and ranked accordingly; return is measured by source and by sector; segments are reported only where available (no `DiscoverySegment` row → empty breakdowns); redundant co-discovered sources are identified with `redundancy_rate == 1`; non-overlapping sources verdict `NOT_REDUNDANT`; a discovery outside the comparison window is excluded.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- `alembic heads`: passed, single head unchanged (no migration in this EPIC).

### Acceptance Criteria

- [x] Every candidate has a discovery source (structural: every row starts from a `DiscoveryRecord`).
- [x] Discovery-to-recommendation funnel metrics are reproducible (deterministic aggregation, no randomness).
- [x] Discovery-to-success metrics are calculated only from completed outcomes (`evaluated_count`/`success_rate` only from rows with an `OutcomeMeasurement`).
- [x] Metrics are segmented by market, sector, size, and industry where applicable (`by_regime`/`by_sector`/`by_market_cap_bucket`/`by_industry`, all "where available").
- [x] Small samples are explicitly marked insufficient (`VERDICT_INSUFFICIENT_SAMPLE` on both success and redundancy verdicts).
- [x] Discovery sources can be ranked objectively (`rank_discovery_sources`, fixed deterministic rule).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including concrete proof of weak-vs-strong source identification, redundancy detection, and common-period window exclusion. This EPIC composes M1.28's funnel vocabulary, M1.16's evidence-gating constants, M1.25's window abstraction, M1.34's persisted segmentation, and M1.38's outcome measurement rather than duplicating any of them, while adding genuinely new return-magnitude and redundancy measures M1.28 did not cover. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->