# EPIC-M1.74 — Evidence Completeness & Point-in-Time Data Quality

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Establish a single evidence-quality gate that determines whether market, fundamental, news and event information is sufficiently fresh, complete, attributable and point-in-time safe for recommendation use.

## Scope
- Define evidence completeness by category and recommendation horizon.
- Validate source provenance, freshness and as-of timestamps.
- Detect stale, missing, conflicting and future-dated evidence.
- Validate point-in-time safety for historical replay and live decisions.
- Produce deterministic evidence-quality status and reason codes.
- Feed evidence-quality state into confidence/recommendation qualification without inventing missing data.
- Preserve immutable quality decisions alongside evidence snapshots.
- Add leakage, freshness, completeness and conflict tests.

## Non-goals
- Creating new data sources.
- Replacing M1.48 evidence snapshots.
- Automatically repairing missing evidence.
- Trading execution.

## Acceptance Criteria
- Every recommendation can report evidence quality by category.
- Future information is rejected from historical decisions.
- Stale or missing evidence is explicit.
- Evidence quality can lower confidence or prevent recommendation publication when policy requires.
- Quality decisions are reproducible and auditable.
- Tests prove point-in-time and freshness safety.

## Dependency Chain
**Previous:** M1.72 Fundamental Data Ingestion + M1.73 News & Event Intelligence + M1.48 Recommendation Evidence Snapshot + M1.54 Evidence Freshness & Revalidation.
**Next:** M1.75 Short-Horizon Probability & Outcome Distribution.

## Execution Rule
Existence of data does not make it trustworthy. This EPIC is the mandatory quality gate before newly ingested evidence materially influences short-horizon prediction.
