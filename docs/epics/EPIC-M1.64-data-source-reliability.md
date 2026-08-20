# EPIC-M1.64 — Data Source Reliability

Status: APPROVED
Execution Status: READY_FOR_EXECUTION

## Objective
Measure the freshness, completeness, availability, and historical reliability of every external information source used by recommendations.

## Scope
- Track source freshness and latency.
- Track completeness and failures.
- Track source coverage.
- Record source reliability metrics.
- Expose evidence-quality status to downstream confidence calculations.

## Acceptance Criteria
- Every external evidence item has source and timestamp metadata.
- Stale or unavailable sources are explicitly identified.
- Reliability metrics are reproducible.
- Low-quality evidence cannot silently receive full trust.

## Dependencies
Previous: M1.63.
Next: M1.65.

## Completion Report
Update this EPIC with final implementation evidence before merge.
