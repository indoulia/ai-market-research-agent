# EPIC-M1.134 — Opportunity Explorer

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Track:** UI + API
**Priority:** P0

## Objective
Allow users to efficiently discover and compare positive opportunities across the full analyzed universe without cluttering the home dashboard.

## UI Scope
- Search by symbol/name.
- Filter by market, horizon, sector, industry, market cap, liquidity and minimum Trust.
- Sort by Trust, score, upside, probability, freshness and ranking.
- Dense responsive data grid on web; compact cards/list on mobile.
- Pagination/infinite loading.
- Saved filter state within session.
- Clear indication of result count and data freshness.
- Drill into recommendation detail.

## API Contract
`GET /api/v1/opportunities`

Query parameters:
`market`, `horizon`, `sector`, `industry`, `marketCap`, `minTrust`, `minScore`, `minUpside`, `liquidityBucket`, `status`, `sort`, `page`, `pageSize`.

Response:
- `items[]`
- `page`
- `pageSize`
- `total`
- `asOf`
- `filters`

Items expose the same canonical recommendation summary contract as M1.133.

## Acceptance Criteria
- Filtering and sorting are server-side.
- Pagination is deterministic.
- Only positive-eligible opportunities are returned by default.
- API and UI handle empty results without visual clutter.
- Filter combinations do not require separate endpoint implementations.
