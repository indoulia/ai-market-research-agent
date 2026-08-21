# EPIC-M1.119 — Real-Time Prediction Outcome Monitor

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Continuously monitor active positive recommendations and determine target hits, stop-loss hits, horizon expiry, material price movements and prediction invalidation in a timely, auditable and provider-independent manner.

## Scope
- Monitor active predictions during applicable market sessions.
- Fetch price updates through market-data provider contracts.
- Evaluate target and stop-loss conditions without waiting for end-of-day processing.
- Record exact detection timestamp, observed price, provider and prediction version.
- Handle gaps, missing ticks, market halts, circuit limits and stale prices explicitly.
- Close predictions deterministically on target, stop-loss or horizon expiry.
- Detect material movements that should trigger re-analysis.
- Detect assumption invalidation and request prediction revision where policy requires.
- Preserve every prediction revision and outcome event immutably.
- Feed completed outcomes into the longitudinal tracking and learning pipeline.

## Outcome States
- ACTIVE
- TARGET_HIT
- STOP_LOSS_HIT
- HORIZON_EXPIRED
- INVALIDATED
- DATA_UNRESOLVED

User-facing recommendation output remains positive-only; negative/cautious states are internal lifecycle states, not recommendation categories.

## Acceptance Criteria
- Target/SL detection is independent of EOD processing.
- Detection is deterministic for identical price/event streams.
- Exact outcome timestamps and evidence are preserved.
- Stale/missing market data cannot silently close a prediction.
- Price gaps are handled according to an explicit outcome policy.
- Outcome closure is idempotent.
- Every closed prediction becomes available to usefulness, attribution, Trust Score and learning systems.

## Dependencies
M1.47, M1.75, M1.78, M1.95, M1.98, M1.118.

## Architectural Rule
**Outcome monitoring must never mutate historical prediction versions; it appends immutable outcome evidence.**
