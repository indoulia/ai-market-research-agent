# EPIC-M1.135 — Recommendations Query API

**Track:** API
**Status:** VALIDATING
**Execution Status:** IMPLEMENTED_PR_OPEN
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

**Dependency note (2026-08-21):** M1.132/M1.87/M1.99 are `DONE`. M1.124
(portfolio-aware utility/correlation) is still `APPROVED`/not implemented.
This EPIC's response `score`/ordering therefore reflects M1.87's
per-opportunity composite ranking only; no portfolio-level
concentration/correlation adjustment is applied yet. The endpoint reads
M1.87's existing `PositiveOpportunityRanking` snapshot unchanged, so
wiring M1.124's adjustment in later requires no contract change here.

## Completion Report (2026-08-21)

**Implemented:** `GET /api/v1/recommendations` (cursor-paginated), composing existing, already-merged domain modules -- nothing recomputed:
- `api/services/recommendations.py::list_recommendations` reads the *latest* `included=True` batch of M1.87's `PositiveOpportunityRanking`, joined to the M1.15 `RecommendationLifecycle` (open states only -- `ISSUED`/`AWAITING_HORIZON` -- so evaluated/closed recommendations don't leak into the live feed; historical access is M1.137's job), M1.77's latest `PredictionTrustScore` (max-id-per-prediction, matching `get_trust_score_history`'s own "latest = last by id" convention), M1.16's `ConfidenceQualityClassification` (current rule version) for `uncertaintyLevel`, and M1.47's `RecommendationPublication` (current methodology version) for `targetPrice`/`stopLoss`/`upsidePct`, falling back to the raw prediction's own `target_return`/`stop_return` when unpublished so a row is never dropped for that reason.
- Filters: `horizon`, `market` (case-insensitive exchange), `sector`, `industry`, `marketCapBucket` (`LARGE_CAP`/`MID_CAP`/`SMALL_CAP` -- a versioned threshold policy this API layer owns, `MARKET_CAP_BUCKET_VERSION = "MCB-001"`, since no existing domain module defines one), `minScore`, `minTrust`. All applied server-side in SQL (AC: "filters are server-side and deterministic").
- Sort: `score|trust|upside|confidence|updatedAt` x `direction=asc|desc`; unknown `sort`/`direction` values reject with `MRA_VALIDATION_FAILED` (reusing M1.132's `ApiError` vocabulary).
- **Real cursor (keyset) pagination**, not offset-based: `api/schemas/common.py::CursorEnvelope`/`CursorMeta` + `api/envelope.py::cursor_paginated` (new envelope variant alongside M1.132's page-based one, documented in `docs/api/VERSIONING.md`). The cursor encodes `(sort_value, id)`, base64/JSON, and the WHERE-clause keyset comparison is built generically per sort field (`api/services/recommendations.py::_keyset_predicate`). A hard `id != cursor_id` guard closes a real bug found in testing: SQLite stores `Numeric` columns as raw floats while SQLAlchemy quantizes the Python-side `Decimal` to the column's declared scale on read, so a cursor value derived from that quantized `Decimal` can differ from a row's true stored value by <1e-6 -- enough to make the previous page's own last row spuriously re-qualify for the next page without the guard. Covered by `test_cursor_pagination_covers_every_row_exactly_once` (5 distinct-sector rows, `pageSize=2`, walks every page and asserts each symbol appears exactly once).
- `fundamentalSummary`/`newsSummary`/`eventSummary`/`marketSummary`: explicitly best-effort "latest available" single-record lookups (`FundamentalDataRecord`, `NewsEventRecord`, `CorporateAction`, `MarketRegime` for the recommendation's own scan) -- not point-in-time-audited evidence snapshots, and `None` (never fabricated) when no record exists.
- `evidenceFreshness`: `FRESH`/`STALE`/`UNKNOWN` from M1.48's `RecommendationEvidenceItem` (`UNKNOWN` when no evidence item was ever recorded for the prediction, `STALE` if any recorded category `is_stale`) -- stale data is identified, never silently presented as current (AC).
- `recommendation` is the fixed literal `POSITIVE_OPPORTUNITY` (`api/schemas/recommendations.py::RECOMMENDATION_LABEL`) -- the only category this platform emits, per the product's positive-only constraint.
- `predictionVersion` carries every version tag needed for replay (`modelVersion`, `featureVersion`, `consensusContractVersion`, `horizonSelectionVersion`, `scoringContractVersion`, `rankingVersion`) (AC: "all displayed values carry the prediction/evidence version required for replay").
- `bootstrap.capabilities.recommendations` flipped to `true`.

**Tests:** `tests/test_api_recommendations.py` (12 new tests) -- empty feed, full-field shape, positive-only filtering (gate-passed vs. ranked-but-excluded), open-vs-closed lifecycle exclusion, default score-descending ordering, horizon filter, `minScore` filter, `sort=trust&direction=asc`, cursor pagination covering every row exactly once across pages, stale-evidence reporting, and both `sort`/`cursor` validation-error paths. Plus 1 updated assertion in `tests/test_api_contract.py` (`capabilities.recommendations` now `true`).

**Validation run:**
```
DATABASE_URL="postgresql+psycopg://ci:ci@localhost/market_agent" python -m pytest -q
# 956 passed, 6 skipped -- full existing suite plus the 12 new tests, no regressions.
```

**Explicitly deferred (named, not fabricated):** ETag/Last-Modified caching (still no endpoint needs it yet); M1.124's portfolio-level ranking adjustment (see Dependencies note above); real authentication enforcement (M1.145).
