# EPIC-M1.34 — Discovery Segmentation

**Status:** DONE
**Execution Status:** COMPLETED
**Priority:** P1

## Objective
Make discovery systematic across market, sector, market-cap, industry, liquidity, and other approved universe dimensions.

## Scope
- Define market-cap buckets.
- Define sector and industry dimensions.
- Define liquidity eligibility.
- Support configurable discovery coverage by segment.
- Record segment membership at discovery time.
- Prevent over-concentration in a single segment.
- Preserve segment metadata for later performance analysis.

## Acceptance Criteria
- [ ] Every discovered candidate has market-cap, sector, industry, and liquidity metadata where available.
- [ ] Discovery can run independently by segment.
- [ ] Segment coverage is measurable per discovery run.
- [ ] Duplicate candidates across segments are consolidated.
- [ ] Segment metadata is snapshot-based and historically preserved.
- [ ] Discovery segmentation does not itself qualify a recommendation.

## Dependencies
**Previous:** M1.33
**Next:** M1.35

## Completion Report

### Status

IMPLEMENTED

### EPIC

EPIC-M1.34

### Branch

autonomous/epic-m1-34, branched cleanly from `main` (declared dependency M1.33 is already merged).

### Objective

Give every discovered candidate a market-cap/sector/industry/liquidity segment snapshot at the moment of discovery, measure segment coverage per discovery run, and detect (never enforce against) over-concentration -- without changing what gets discovered or how it qualifies.

### Design Decisions

- **Two new `Stock` columns, `industry` and `market_cap`** (migration `0017`), alongside the existing `sector` column -- these are static classification attributes of a stock, the same category `sector` already was, not per-scan computed features. No ingestion process in this repo currently populates them (there is no market-cap/industry data source yet), so they default to `None`/`UNCLASSIFIED` for every current stock; that is expected and handled explicitly rather than silently.
- **New table `discovery_segments`** (one row per `discovery_record_id`, unique): an immutable snapshot of `market_cap_bucket`, `sector`, `industry`, `liquidity_bucket`, and `segmentation_rule_version` at discovery time. Immutability is enforced the same way as `PredictionOutcome`/`RecommendationGeneration`/`WatchlistEvaluation` (a `before_update` guard raising `DiscoverySegmentImmutableError`) -- this is the scope item "segment metadata is snapshot-based and historically preserved": a stock's `sector`/`market_cap` can be corrected or reclassified later without rewriting what segment a past discovery belonged to (proven directly by `test_recording_segment_twice_is_idempotent_and_keeps_the_original_snapshot`).
- **`classify_market_cap_bucket`/`classify_liquidity_bucket`** (`app/discovery_segmentation.py`): fixed, documented, versioned threshold constants (`SEGMENTATION_VERSION = "SEG-001"`), first-match-wins descending scan, `None` input -> explicit `UNCLASSIFIED` rather than a fabricated bucket or omission (scope item 1, "where available"). `sector`/`industry` pass through `Stock`'s own fields the same way, defaulting to `UNCLASSIFIED` when absent.
- **Liquidity buckets are deliberately distinct constants from M1.8's `MIN_VOLUME_RATIO_20D` pass/fail floor**, even though both read `volume_ratio_20d`: M1.8's threshold is a qualification gate, this EPIC's is a descriptive segment for coverage measurement -- conflating them would let a segmentation-constant change accidentally alter recommendation qualification, which the non-goals explicitly forbid.
- **"Prevent over-concentration in a single segment" is implemented as detection, not enforcement:** `over_concentrated_segments(coverage, total, max_share=DEFAULT_MAX_SEGMENT_SHARE)` flags which segment keys exceed a fixed share of one discovery run's candidates. It does not filter, drop, or reorder any candidate -- doing so would be a qualification-rule change, which is out of scope. This is a documented design decision open to reviewer adjustment.
- **"Discovery can run independently by segment"** is implemented as `discovery_records_in_segment(session, scan_id, *, market_cap_bucket=None, sector=None, industry=None, liquidity_bucket=None)` -- a post-hoc filter over one scan's already-discovered, already-segmented candidates, rather than re-running M1.12's universe scan per segment. M1.12 already scans every active stock in one pass regardless of segment, so a separate per-segment scan would be redundant; filtering the single pass's results by segment is equivalent and simpler. Documented here for reviewer scrutiny.
- **`record_segments_for_scan(session, scan_id)`** composes over every `DiscoveryRecord` already persisted for a scan (e.g. by M1.33's `record_discovery_for_scan`) via a left join to `ScanCandidate` (for `volume_ratio_20d`) and an inner join to `Stock` (for `sector`/`industry`/`market_cap`) -- callable right after M1.33's discovery step in a scheduler pipeline without modifying M1.33's already-merged module at all.
- **Duplicate consolidation (scope item 4)** needed no new code: `DiscoveryRecord`'s own `(scan_id, stock_id, source)` uniqueness (M1.17) and `DiscoverySegment`'s own `discovery_record_id` uniqueness together mean a stock can never get two discovery or segment rows for the same scan, regardless of how many segment dimensions it happens to match.
- **"Discovery segmentation does not itself qualify a recommendation"** holds by construction: nothing in this module writes to `Prediction`, `RecommendationGeneration`, or `RecommendationSelection`, and nothing in M1.13/M1.14 reads `DiscoverySegment`.

### Files Changed

- `app/discovery_segmentation.py` — new: classification functions, `record_segment_for_discovery`, `record_segments_for_scan`, `segment_coverage_for_scan`, `over_concentrated_segments`, `discovery_records_in_segment`.
- `app/models.py` — new `DiscoverySegment` model; `Stock` gains `industry`, `market_cap`.
- `migrations/versions/0017_discovery_segments.py` — new migration.
- `tests/test_discovery_segmentation.py` — new: 9 tests.
- `docs/epics/EPIC-M1.34-discovery-segmentation.md` — this completion report.

### Tests Executed

- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -q`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m pytest -v tests/test_discovery_segmentation.py`
- `"C:/Users/prsingh/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q app scripts tests migrations`
- `git diff --check`
- `alembic heads` (single clean head, `0017_discovery_segments`)
- Migration validation against the local `market_agent` PostgreSQL database: `upgrade head` from `0016` through `0017` (verified `discovery_segments` created and the two new `stocks` columns present), `downgrade -1` (verified table dropped and columns removed), `upgrade head` again (clean re-apply). `current` confirmed `0017_discovery_segments` throughout.

### Test Results

- `pytest -q`: **189 passed, 0 failed** (180 pre-existing from `main` + 9 new).
- `pytest -v tests/test_discovery_segmentation.py`: **9 passed** — market-cap and liquidity bucket boundaries are exact (inclusive lower bounds, correct fallthrough); a full snapshot (sector/industry/market-cap/liquidity) is recorded correctly from real `Stock`/`ScanCandidate` data; missing metadata is recorded as explicit `UNCLASSIFIED` rather than omitted; re-segmenting the same discovery after the underlying `Stock.market_cap` changed still returns the *original* snapshot (proving history isn't rewritten); a direct mutation attempt after creation raises `DiscoverySegmentImmutableError`; `record_segments_for_scan` covers every discovery record in a scan; segment coverage counts are correct and `over_concentrated_segments` correctly flags an 8-of-10 sector as over-concentrated while leaving the 2-of-10 sector unflagged; and `discovery_records_in_segment` correctly filters one scan's results to just one sector.
- `compileall -q app scripts tests migrations`: passed, no output (exit 0).
- `git diff --check`: passed, no output (exit 0).
- Migration chain and round-trip: passed as detailed above.

### Acceptance Criteria

- [x] Every discovered candidate has market-cap, sector, industry, and liquidity metadata where available (explicit `UNCLASSIFIED` when not available, never omitted).
- [x] Discovery can run independently by segment (`discovery_records_in_segment`).
- [x] Segment coverage is measurable per discovery run (`segment_coverage_for_scan`).
- [x] Duplicate candidates across segments are consolidated (inherited from `DiscoveryRecord`/`DiscoverySegment` uniqueness, no candidate can appear twice regardless of segment).
- [x] Segment metadata is snapshot-based and historically preserved (immutability guard + proven by test).
- [x] Discovery segmentation does not itself qualify a recommendation (no write path to `Prediction`/`RecommendationGeneration`/`RecommendationSelection`).

### Claude Assessment

I believe this implementation satisfies all six acceptance criteria with real, verified evidence, including a real-Postgres migration round-trip. Two scope items required genuine design judgment, both documented above for reviewer scrutiny: treating "prevent over-concentration" as detection rather than enforcement (to avoid the non-goal of changing qualification rules), and treating "run independently by segment" as post-hoc filtering of one universe-wide scan rather than a separate scan per segment. `market_cap`/`industry` are currently unpopulated for every existing stock since no ingestion path sets them yet -- that's a data-availability gap for a future EPIC, not a defect in this one. Per the user's standing-contract update, Claude will merge this PR once CI is green and it is cleanly mergeable, then continue to the next eligible EPIC.

## Review History

<!-- ChatGPT: append review decisions; never erase prior findings. -->