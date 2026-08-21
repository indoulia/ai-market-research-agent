# EPIC-M1.124 — Portfolio-Aware Opportunity Utility & Correlation

**Status:** VALIDATING
**Execution Status:** IMPLEMENTED_PENDING_MERGE
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

## Completion Report

### Status
Implemented, tested, PR pending. Branch `autonomous/epic-m1-124`.

### What was built
- `app/portfolio_opportunity_correlation.py` (PCR-001/PUA-001/PSE-001):
  - `assess_portfolio_correlation`: for one scan's M1.9-qualified candidates, computes real Pearson
    correlation of trailing daily returns already stored in `MarketPrice` (no fabricated
    correlation matrix), plain sector-count concentration against `Stock.sector`, and flags a pair
    "near-duplicate" only when it is both same-sector *and* above `HIGH_CORRELATION_THRESHOLD`.
    Idempotent by `(scan_id, evaluated_at)`.
  - `apply_portfolio_adjustment`: layers a deterministic, versioned concentration/correlation
    penalty onto M1.87's already-persisted `composite_score` (read via the scan's
    `PositiveOpportunityRanking` rows), optionally cost-scaled by M1.98's `ExecutionCostAssessment`
    net/gross return ratio when one exists. Writes only new `PortfolioUtilityAssessment` rows --
    never touches `Prediction`, `PositiveOpportunityRanking` or any other system-wide field, so
    individual prediction quality stays separately measurable (AC). Idempotent by
    `(prediction_id, evaluated_at)`.
  - User preference support: reuses M1.31's `UserPreference.preferred_sectors` read-only -- a
    sector outside a given user's stated preference excludes that user's own adjusted selection,
    never `Prediction` or the scan's global ranking (AC: "user preferences affect selection
    policy, not global prediction truth").
  - `measure_portfolio_selection_effectiveness`: compares the diversified/adjusted top-K's
    realized success rate against M1.87's raw composite-ranked top-K over the same
    `PredictionOutcome` evidence, mirroring M1.99's `measure_ranking_effectiveness` pattern
    (honestly `INSUFFICIENT_SAMPLE` below `MIN_SAMPLE_SIZE_FOR_COMPARISON`).
- `app/models.py`: new `PortfolioCorrelationReport`, `PortfolioUtilityAssessment`,
  `PortfolioSelectionEffectivenessReport` models.
- `migrations/versions/0101_portfolio_opportunity_correlation.py`.
- `tests/test_portfolio_opportunity_correlation.py`: 9 tests covering correlation+sector
  near-duplicate detection, uncorrelated/different-sector no-flag case, correlation-report
  idempotency, concentration penalty without raw-ranking mutation, utility-assessment
  idempotency, user-preference exclusion without global-ranking impact, cost-aware vs.
  cost-unavailable base utility, and insufficient-sample effectiveness reporting.

### Known gaps, honestly scoped
- **Liquidity** beyond M1.98's own `liquidity_bucket`/net-return cost-scaling (true order-book
  microstructure) is M1.128's domain, not yet implemented on this platform -- not fabricated
  here.
- **Benchmark-relative value**: M1.129 (benchmark-relative opportunity alpha) merged during this
  EPIC's implementation but is not a declared dependency of M1.124, so it is deliberately not
  read here -- wiring it into the utility function is left as explicit future work for whichever
  EPIC formally adopts that dependency.
- Correlation is computed from daily-bar returns (this platform's only price granularity, per
  Yahoo Finance), not intraday/factor-model correlation.

### Tests
`python -m pytest tests/test_portfolio_opportunity_correlation.py -q` -- 9 passed.
`python -m alembic heads` -- single clean head at `0101_portfolio_correlation`.
`python -m pytest tests/test_fresh_database_migration.py tests/test_recommendation_history_db_integrity.py -q` -- 9 passed.
