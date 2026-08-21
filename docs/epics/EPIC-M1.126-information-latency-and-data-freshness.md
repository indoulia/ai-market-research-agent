# EPIC-M1.126 — Information Latency & Data Freshness Intelligence

**Status:** DONE
**Execution Status:** COMPLETED
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

## Completion Report

### Status
Implemented, tested, merged via PR #244.

### What was built
- `app/information_latency.py` (ILT-001/LDR-001):
  - `assess_information_latency`: for each `STATUS_AVAILABLE` evidence category (M1.48), computes
    decision latency (`Prediction.as_of_timestamp - evidence_timestamp`) and judges it against
    M1.35's own `FRESHNESS_POLICY` threshold tightened by `horizon_adjusted_threshold` -- a fixed,
    documented SLA multiplier by horizon tier (0.5x at horizon<=1 day, 0.75x at <=3, 1.0x
    otherwise), so the same raw staleness number is judged against a stricter bar for a
    short-horizon prediction than a long-horizon one (AC: "freshness policy differs appropriately
    by capability and prediction horizon"). A missing `evidence_timestamp` is flagged, never
    silently treated as fresh (AC: "stale data cannot silently appear current"). Read-only,
    propose-only: `suppress_eligibility` has no write path to `Prediction` or any gate table --
    wiring an actual gate is left to a future consuming EPIC, the same posture M1.112 took before
    M1.119 became its first consumer this session. Idempotent by `(prediction_id, evaluated_at)`.
  - `measure_latency_degradation`: compares one window's average ingestion latency
    (`DataFetchAttempt.requested_at - source_timestamp`, M1.35) against a baseline window's, per
    data type, mirroring M1.99's `measure_ranking_effectiveness` comparison pattern (honestly
    `INSUFFICIENT_SAMPLE` below `MIN_SAMPLE_SIZE_FOR_COMPARISON` on either side). Always persists a
    fresh, independent report -- never mutates a prior one (AC: "historical freshness values are
    immutable").
- `app/models.py`: new `InformationLatencyAssessment`, `LatencyDegradationReport` models.
- `migrations/versions/0101_information_latency.py`.
- `tests/test_information_latency.py`: 9 tests covering SLA-multiplier tiering, within-SLA vs.
  short-horizon-tightened-SLA violation, missing-timestamp flagging, idempotency, and
  degradation-report insufficient-sample/degraded/improved verdicts.

### Known gap, honestly scoped
"Provider latency" and "ingestion latency" are named separately in the EPIC's own scope, but this
platform's only provider (Yahoo Finance) exposes no distinct "provider-receipt" timestamp separate
from "when MRA fetched it" -- there is no real second gap to measure. `_ingestion_latency`
(`DataFetchAttempt.requested_at - source_timestamp`) is the one real, measurable stage; a future
EPIC that integrates a provider exposing its own receipt timestamp would extend this, not replace
it.

### Tests
`python -m pytest tests/test_information_latency.py -q` -- 9 passed.
`python -m alembic heads` -- single clean head at `0101_information_latency`.
`python -m pytest tests/test_fresh_database_migration.py tests/test_recommendation_history_db_integrity.py -q` -- 9 passed.
