# EPIC-M1.135 — Recommendations Query API

**Track:** API
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Expose the ranked positive-only MRA recommendation feed to Flutter with all information required for compact cards, filters and sorting.

## Contract
`GET /api/v1/recommendations`

Query:
- `horizon=1|2|3|5|7`
- `market=nse|...`
- `sector`
- `industry`
- `marketCapBucket`
- `minScore`
- `minTrust`
- `sort=score|trust|upside|confidence|updatedAt`
- `direction=asc|desc`
- `pageSize`
- `cursor`

Response item:
`id, symbol, exchange, companyName, asOf, price, changePct, recommendation, horizonDays, targetPrice, stopLoss, upsidePct, probability, score, confidence, trustScore, uncertaintyLevel, fundamentalSummary, newsSummary, eventSummary, marketSummary, evidenceFreshness, status, predictionVersion, updatedAt`

Only positive eligible recommendations may be returned.

## Acceptance Criteria
- Results are already ranked according to the server policy.
- Filters are server-side and deterministic.
- Pagination is cursor-based and stable during a query session.
- All displayed values carry the prediction/evidence version required for replay.
- Stale data is identified rather than silently presented as current.
- Contract tests cover empty, large, stale and mixed-filter cases.

## Parallelization
API implementation. Flutter consumes this exact contract; no UI-side business ranking.

## Dependencies
M1.132, M1.87, M1.99, M1.124.
