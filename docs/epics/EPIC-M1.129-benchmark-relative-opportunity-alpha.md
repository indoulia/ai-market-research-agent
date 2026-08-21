# EPIC-M1.129 — Multi-Level Benchmark-Relative Opportunity Intelligence

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Determine whether a recommendation creates genuine stock-specific value relative to its industry, sector and broad-market benchmarks rather than simply benefiting from a rising market.

## Scope
- Compare stock performance with industry, sector and broad-market benchmarks.
- Calculate benchmark-relative return and alpha-like measures using appropriate methodology.
- Evaluate target/SL outcomes relative to benchmark behavior over the same horizon.
- Preserve benchmark membership and methodology versions.
- Segment prediction quality by benchmark-relative environment.
- Feed relative opportunity into ranking and usefulness measurement.

## Acceptance Criteria
- Every eligible closed recommendation can be evaluated against relevant benchmarks.
- Benchmark comparisons use point-in-time appropriate benchmark membership/data.
- Raw stock return and relative performance remain separate metrics.
- Ranking can prefer genuine relative opportunities according to policy.
- Historical benchmark methodology is reproducible.

## Dependencies
M1.86, M1.98, M1.99, M1.109.
