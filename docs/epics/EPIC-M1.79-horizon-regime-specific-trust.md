# EPIC-M1.79 — Horizon & Regime-Specific Trust

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Approved By:** User
**Priority:** P0

## Objective
Measure prediction trust separately by forecast horizon and market regime so MRA can publish stronger opportunities only where its historical evidence supports them.

## Scope
- Maintain trust by 1/2/3/5/7 trading-day horizon.
- Maintain trust by supported market regime.
- Combine horizon and regime evidence when sample sizes permit.
- Preserve sample size and uncertainty.
- Feed trust into positive-only recommendation gating.
- Recalculate as new outcomes arrive without rewriting historical trust.

## Acceptance Criteria
- Trust can differ by horizon and regime.
- Insufficient samples are explicit.
- Historical values remain immutable.
- Low-trust combinations can suppress recommendations.
- Tests cover horizon/regime boundaries and sparse data.

## Dependency Chain
**Previous:** M1.77, M1.78, M1.26.
**Next:** M1.80, M1.81, M1.84.
