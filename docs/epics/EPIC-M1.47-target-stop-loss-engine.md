# EPIC-M1.47 — Recommendation Target & Stop-Loss Engine

**Status:** READY_FOR_APPROVAL  
**Execution Status:** READY_FOR_EXECUTION  
**Priority:** P1  
**Dependency:** M1.14

## Objective
Produce explicit, internally consistent target price, stop-loss, upside percentage, downside percentage, horizon, and reward/risk values for every published recommendation.

## Scope
- Calculate target and stop-loss using horizon-appropriate evidence.
- Derive upside/downside percentages from the stored reference price.
- Validate reward/risk and numerical consistency before publication.
- Record target/SL methodology and version.
- Freeze published values; later changes become a new recommendation version.

## Acceptance Criteria
- Every published recommendation has target, SL, horizon, upside %, downside %, and reward/risk where applicable.
- Derived percentages reconcile exactly with stored prices.
- Invalid or contradictory values prevent publication.
- Target/SL calculation is deterministic for the same inputs and version.
- Historical recommendations retain their original values.
- Tests cover normal, boundary, and invalid cases.

## Dependency Chain
M1.14 → M1.47 → M1.48/M1.50+

## Completion Report
<!-- Claude: populate only after implementation. Preserve review history. -->
