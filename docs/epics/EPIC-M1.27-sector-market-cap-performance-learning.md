# EPIC-M1.27 — Sector & Market-Cap Performance Learning

**Status:** READY_FOR_APPROVAL  
**Execution Status:** NOT_STARTED  
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
**Previous:** M1.16, M1.21, M1.26  
**Next:** M1.29, M1.30

## Completion Report
`docs/epics/EPIC-M1.27-sector-market-cap-performance-learning.md`
