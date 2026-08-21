# EPIC-M1.72 — Fundamental Data Ingestion

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Approved By:** User
**Priority:** P0

## Objective
Provide a real, production-capable, point-in-time fundamental-data ingestion pipeline so recommendation evidence can use actual company financial information instead of recording fundamentals as UNAVAILABLE.

## Scope
- Define the supported fundamental-data contract and source provenance.
- Ingest revenue, earnings/EPS, margins, profitability, leverage, cash flow and valuation fields where available.
- Preserve publication/effective timestamps and as-of semantics.
- Handle revised filings without rewriting historical snapshots.
- Normalize company/security identifiers.
- Record fetch attempts, freshness, source, completeness and failures.
- Expose immutable fundamental evidence snapshots to the existing evidence layer.
- Add deterministic tests for freshness, missing data, revisions and point-in-time safety.

## Non-goals
- Replacing the recommendation scoring model.
- Automatically trading.
- Fabricating unavailable fundamental fields.

## Acceptance Criteria
- Real fundamental data can be ingested and persisted with provenance.
- Historical recommendations can only see fundamentals available at their decision time.
- Revisions do not mutate prior evidence snapshots.
- Missing/failed data is explicit.
- M1.48 can consume real fundamental evidence instead of defaulting to UNAVAILABLE when data exists.

## Dependency Chain
**Previous:** M1.35 Information Refresh Policy, M1.48 Recommendation Evidence Snapshot.
**Next:** M1.74 Evidence Completeness & Point-in-Time Data Quality.

## Execution Rule
Do not mark fundamental evidence trustworthy until source coverage, freshness, provenance and point-in-time behavior are demonstrated.
