# EPIC-M1.135 — Recommendation Detail & Prediction Timeline

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Provide a compact but complete view of a recommendation's current prediction, evidence, revisions, target/SL/horizon and outcome history.

## UI Scope
- Header with symbol, price, positive recommendation state and freshness.
- Metric grid: horizon, target, SL, upside, score, probability/confidence, Trust and uncertainty.
- Price/target/SL chart.
- Fundamental, technical, market, news and event evidence sections.
- Why MRA selected this opportunity.
- What changed since previous prediction.
- Prediction-version timeline with timestamps and reasons.
- Active/outcome status.
- Feedback action.
- Progressive disclosure so detail remains uncluttered.

## API Contract
`GET /api/v1/recommendations/{recommendationId}`
`GET /api/v1/recommendations/{recommendationId}/timeline`
`GET /api/v1/recommendations/{recommendationId}/evidence`
`GET /api/v1/recommendations/{recommendationId}/outcome`

Recommendation detail must include:
- immutable prediction version identifier
- current values
- `createdAt`, `updatedAt`, `asOf`
- evidence references
- provider/source provenance
- model/configuration versions
- lifecycle state

Timeline returns ordered immutable revisions with change reason and affected metrics.

## Acceptance Criteria
- Historical revisions cannot be overwritten.
- User can reconstruct why target/SL/confidence/Trust changed.
- Evidence is linked to source and timestamp.
- Target/SL/outcome states are consistent with M1.119.
- UI remains usable on mobile and desktop.
