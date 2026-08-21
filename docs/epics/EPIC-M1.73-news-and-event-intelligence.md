# EPIC-M1.73 — News & Event Intelligence

> **Note (2026-08-21 QA/integration audit):** This file duplicates
> `EPIC-M1.73-news-event-intelligence.md`, which is `DONE` with a real,
> verified implementation (`app/news_data/{ingest,yahoo}.py`). No EPIC
> numbered ≥110 references this file or depends on it as unfinished work.
> Left in place, not deleted/renamed — a human should decide whether to
> formally retire it.

**Status:** READY_FOR_APPROVAL
**Execution Status:** BLOCKED_PENDING_APPROVAL
**Priority:** P0

## Objective
Create a real, provenance-aware news and corporate-event pipeline for short-horizon recommendation decisions.

## Scope
- Ingest supported news and event sources.
- Resolve articles/events to securities and companies.
- Deduplicate repeated reports.
- Capture publication time, ingestion time and source provenance.
- Classify event type and materiality.
- Determine horizon relevance and affected securities.
- Track source reliability using M1.64.
- Preserve immutable evidence snapshots.
- Surface conflicting evidence through M1.65 rather than silently selecting one source.
- Support earnings/results, dividends, splits, corporate announcements and other material events where supported.

## Non-goals
- Generic sentiment scoring as the sole decision signal.
- Fabricated event interpretation.
- Automatic trading.

## Acceptance Criteria
- News/events can be fetched and linked to securities with provenance.
- Duplicate reports are collapsed without losing source evidence.
- Materiality and publication time are preserved.
- Event evidence can be consumed by M1.48/M1.54/M1.62.
- Missing or unavailable event/news data remains explicit.

## Dependency Chain
**Previous:** M1.35 Information Refresh Policy, M1.48 Recommendation Evidence Snapshot, M1.63 Event Alerts.
**Next:** M1.74 Evidence Completeness & Point-in-Time Data Quality.

## Execution Rule
No news/event evidence may influence recommendations unless its source, timestamp, security mapping and freshness are known.
