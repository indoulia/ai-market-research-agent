# EPIC-M3.6 — Discovery Intelligence

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Make MRA's continuous discovery visible and explainable without exposing internal implementation complexity.

## UI Scope
- Discovery summary: discovered, analyzed, qualified and published counts.
- Discovery timeline.
- Candidate source/provider indicators.
- Filters by market, sector, industry, size and discovery basis.
- Candidate lifecycle: discovered → analyzed → qualified/suppressed → published.
- Suppression reason available in internal/authorized detail where appropriate.
- Discovery effectiveness summary.

## API Contract
`GET /api/v1/discovery/summary`
`GET /api/v1/discovery/history`
`GET /api/v1/discovery/candidates`

Queries:
`market`, `sector`, `industry`, `marketCap`, `from`, `to`, `page`, `pageSize`.

Candidate response:
`candidateId`, `symbol`, `discoveredAt`, `basis[]`, `stage`, `providerEvidence`, `qualification`, `suppressionReason`, `publishedRecommendationId`.

## Acceptance Criteria
- Discovery history is immutable.
- User can understand why a candidate entered analysis.
- Discovery and recommendation counts reconcile.
- Discovery provider provenance is retained.
- The screen remains compact and avoids dumping internal logs.
