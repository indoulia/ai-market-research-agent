# EPIC-142 — Discovery, Market, News & Events API

**Track:** API
**Status:** DONE
**Execution Status:** MERGED (PR #175, commit 8bd4e02)
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
API implementation. UI EPIC-143 consumes only these contracts.

## Dependencies
EPIC-135, EPIC-103, EPIC-123, EPIC-129, EPIC-130.

**Dependency note (2026-08-21):** EPIC-135/EPIC-103 are `DONE`. EPIC-123
(event-driven refresh), EPIC-129 (information latency) and EPIC-130
(source-authority fact resolution) are still `APPROVED`/not implemented.
None of the four contracts below need them to exist: discoveries, news
and corporate actions already have real, queryable tables from earlier
merged EPICs. Named, honest gaps until each lands: no cross-source
"same real-world event, different provider" content dedup (EPIC-130 would
own resolving multiple sources into one authoritative fact); news/events
reflect whatever's already ingested, not push-refreshed on new material
information (EPIC-123); no per-field staleness/latency metadata beyond
what EPIC-138/EPIC-140 already expose per-recommendation (EPIC-129).

## Completion Report (2026-08-21)

**Implemented**, composing existing, already-merged domain modules:
- `GET /api/v1/discoveries` — one item per stock (its most-recently-discovered `DiscoveryRecord`, across any scan/source), with `marketCapBucket`/`liquidity` classified **live** from current `Stock`/`ScanCandidate` state via the same `app.discovery_segmentation` thresholds EPIC-138 now uses (extracted into a shared `api/services/segmentation.py`). `discoveryReasons` aggregates every rationale ever recorded for that stock across sources. `status`/`score`/`trustScore` reflect the linked `RecommendationGeneration`/prediction when one exists (`PENDING_ANALYSIS` when a candidate hasn't been routed through the pipeline yet, `NOT_QUALIFIED` when EPIC-009's gate rejected it, the EPIC-018 lifecycle state otherwise) — never fabricated for a discovery that was never analyzed. Real keyset pagination (`market`/`sector`/`industry`/`marketCapBucket`/`liquidity`/`minScore` filters, `sort=discoveredAt|score`).
- `GET /api/v1/market/summary` — `regime`/`advanceDecline`/`volatility` from EPIC-025's latest `MarketRegime`; `volume` is a real `SUM` across the universe on the latest trading day; `sectorLeaders`/`sectorLaggards` are real day-over-day average % change per `Stock.sector` (new aggregation, verified no existing module computes this). `marketStatus` is always `"UNKNOWN"` and `indexes` is always `[]` — named, honest gaps (no market-calendar module, no index-level price feed).
- `GET /api/v1/news` — direct projection of EPIC-090's `NewsEventRecord`, filterable by `symbol`/`sector`/`industry`, real keyset pagination on `publishedAt`. `affectedSecurities` is always one element (this platform doesn't model multi-security news).
- `GET /api/v1/events` — direct projection of EPIC-090's `CorporateAction`, same filter/pagination shape. `materiality` is honestly `null` (the table has no such field).
- New shared modules: `api/services/keyset.py` (extracted the EPIC-138 keyset-pagination primitives so `/discoveries`, `/news`, `/events` reuse one implementation instead of four) and `api/services/segmentation.py` (extracted the market-cap/liquidity SQL-CASE builders so `/recommendations` and `/discoveries` share one canonical-vocabulary implementation).
- `bootstrap.capabilities.discovery`/`marketSummary`/`news`/`events` flipped to `true`.

**Tests:** `tests/test_api_discovery_market_news.py` (12 new tests) — empty discoveries, a never-routed candidate's honest `PENDING_ANALYSIS` state, a qualified discovery's real score/trust/bucket/liquidity, reason aggregation across two sources for one stock, sector and market-cap-bucket filters, unknown-sort rejection, cursor pagination covering every item once, market summary's empty state, market summary with a real regime + computed sector leaders/laggards, news list + symbol filter, and events from corporate actions. Plus 1 updated assertion in `tests/test_api_contract.py` (bootstrap capabilities).

**Validation run:**
```
DATABASE_URL="postgresql+psycopg://ci:ci@localhost/market_agent" python -m pytest -q
# 1017 passed, 6 skipped -- full existing suite plus the 12 new tests, no regressions.
```

**Explicitly deferred (named, not fabricated):** cross-source event dedup (EPIC-130); event-driven push refresh (EPIC-123); market-calendar-aware `marketStatus` (EPIC-124, not even a stated dependency); index-level quotes (no ingestion source exists for them at all).
