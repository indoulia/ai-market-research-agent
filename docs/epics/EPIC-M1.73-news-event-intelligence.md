# EPIC-M1.73 — News & Event Intelligence

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Provide production-capable, provenance-aware news and corporate-event intelligence so short-horizon recommendations can use fresh, material and attributable information instead of treating news/events as unavailable or generic sentiment.

## Scope
- Define supported news/event source contracts and provenance.
- Ingest and normalize company-relevant news and corporate events.
- Resolve articles/events to supported securities and companies.
- Deduplicate repeated or syndicated information.
- Capture publication/event timestamps and as-of semantics.
- Classify event type, materiality and horizon relevance.
- Preserve source reliability, freshness, completeness and fetch failures.
- Expose immutable news/event evidence snapshots to M1.48.
- Support evidence conflict handling through M1.65.
- Add deterministic tests for entity resolution, deduplication, freshness, missing data and point-in-time safety.

## Non-goals
- Trading execution.
- Replacing the recommendation scoring model.
- Treating sentiment alone as investment evidence.
- Silently filling unavailable information.

## Acceptance Criteria
- Real news and event data can be ingested with provenance.
- Relevant items are mapped to the correct supported securities.
- Duplicate/syndicated items are handled deterministically.
- Materiality and horizon relevance are persisted.
- Historical analysis cannot see information published after its decision time.
- M1.48 can consume real news/event evidence when available.

## Dependency Chain
**Previous:** M1.35 Information Refresh Policy, M1.48 Recommendation Evidence Snapshot.
**Next:** M1.74 Evidence Completeness & Point-in-Time Data Quality.

## Execution Rule
Do not treat news/event evidence as trustworthy until source provenance, freshness, entity resolution and point-in-time behavior are demonstrated.
