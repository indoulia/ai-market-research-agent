# EPIC-M1.34 — Discovery Segmentation

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
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
Claude must record final segment definitions, tests, coverage evidence, and data-quality limitations.