# EPIC-M1.124 — Portfolio-Aware Opportunity Utility & Correlation

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Ensure MRA's recommendation ranking measures the usefulness of opportunities individually and collectively, accounting for correlation, concentration, sector exposure and overlapping market bets.

## Scope
- Define a configurable opportunity utility function using expected return, probability, Trust, uncertainty, downside, liquidity, execution cost and benchmark-relative value.
- Measure correlation between active and candidate opportunities.
- Detect sector, industry, factor and market-beta concentration.
- Identify duplicate/near-duplicate opportunities that represent the same underlying bet.
- Apply configurable concentration penalties to ranking without changing raw prediction probabilities.
- Measure portfolio-level expected benefit and risk of recommendation sets.
- Preserve ranking snapshots and the reasons opportunities were selected/suppressed.
- Evaluate selection utility historically against individual-stock ranking and benchmark baselines.
- Support user preference constraints without contaminating global model learning.

## Acceptance Criteria
- MRA can identify highly correlated recommendation sets.
- Ranking can prefer a diversified set of strong opportunities over redundant signals when policy requires.
- Individual prediction quality remains separately measurable from portfolio/set utility.
- Utility methodology is versioned and reproducible.
- User preferences affect selection policy, not global prediction truth.
- Historical selection decisions remain reconstructable.

## Dependencies
M1.87, M1.98, M1.99, M1.109, M1.110, M1.115.

## Non-Goal
This EPIC does not authorize automated trading or portfolio execution. It improves recommendation selection and evaluation only.
