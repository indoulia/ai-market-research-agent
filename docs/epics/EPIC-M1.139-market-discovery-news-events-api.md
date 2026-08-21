# EPIC-M1.139 — Discovery, Market, News & Events API

**Track:** API
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Provide query APIs for the discovery universe and the external-world evidence that drives MRA recommendations.

## Contracts
`GET /api/v1/discoveries` — discovered candidates with discovery basis.

Query: `market,sector,industry,marketCapBucket,liquidity,minScore,sort,cursor,pageSize`.

Item: `symbol,companyName,exchange,sector,industry,marketCapBucket,discoveredAt,discoveryReasons,score,trustScore,eligibility,status`.

`GET /api/v1/market/summary` — `asOf,marketStatus,regime,indexes,advanceDecline,volume,volatility,sectorLeaders,sectorLaggards`.

`GET /api/v1/news` — `symbol,headline,source,publishedAt,detectedAt,materiality,affectedSecurities,evidenceId`.

`GET /api/v1/events` — `symbol,type,title,effectiveAt,detectedAt,materiality,source,evidenceId`.

## Acceptance Criteria
- Discovery reasons are explicit and filterable.
- News/events expose source and detection timestamps.
- Duplicate/syndicated events are represented once at the API layer.
- APIs support symbol/sector/industry filtering.
- All timestamps are timezone-aware ISO-8601.
- Provider identity and evidence IDs are available where user-visible provenance is appropriate.

## Parallelization
API implementation. UI M1.140 consumes only these contracts.

## Dependencies
M1.132, M1.103, M1.120, M1.126, M1.127.
