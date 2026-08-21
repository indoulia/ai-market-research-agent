# EPIC-M1.126 — Information Latency & Data Freshness Intelligence

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Measure whether MRA receives, validates and acts on external information quickly enough for the prediction horizon, and prevent stale information from silently supporting active predictions.

## Scope
- Record source-event timestamp, provider-receipt timestamp, MRA-ingestion timestamp and prediction-reaction timestamp.
- Measure provider latency, ingestion latency and decision latency.
- Define freshness SLAs by capability and horizon.
- Detect stale prices, news, fundamentals, events and corporate-action data.
- Route stale requests through configured provider fallback.
- Reduce eligibility or suppress predictions when required freshness cannot be achieved.
- Preserve freshness snapshots with predictions and revisions.
- Track latency distributions and degradation over time.

## Acceptance Criteria
- Every material external input has timestamp/provenance metadata sufficient to measure freshness.
- Freshness policy differs appropriately by capability and prediction horizon.
- Stale data cannot silently appear current.
- Latency degradation is visible and can affect prediction eligibility.
- Historical freshness values are immutable.

## Dependencies
M1.90, M1.93, M1.105, M1.118, M1.120.
