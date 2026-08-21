# EPIC-M1.136 — News & Corporate Events Intelligence

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Show only material news and corporate/event information relevant to the user's opportunities and watched universe, while exposing how events affect predictions.

## UI Scope
- Compact news/events feed.
- Filters by stock, event type, materiality and date.
- Event cards with icon, timestamp, source and affected symbols.
- Materiality indicator.
- Link to affected recommendation and prediction revision.
- Corporate-action and earnings sections.
- Avoid duplicate/syndicated stories.

## API Contract
`GET /api/v1/news`
`GET /api/v1/events`
`GET /api/v1/events/{eventId}`

Query:
`symbol`, `eventType`, `materiality`, `from`, `to`, `page`, `pageSize`.

Event response:
`eventId`, `eventType`, `title`, `summary`, `publishedAt`, `detectedAt`, `effectiveAt`, `materiality`, `affectedSymbols[]`, `sources[]`, `impactStatus`, `predictionRevisionIds[]`.

## Acceptance Criteria
- Materiality and source provenance are visible.
- Duplicate events are collapsed.
- Event timestamps distinguish publication, detection and effective time.
- User can navigate from event to affected prediction.
- Provider/source conflicts remain accessible through detail.
