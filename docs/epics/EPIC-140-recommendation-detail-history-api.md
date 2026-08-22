# EPIC-140 — Recommendation Detail, Revision & History API

**Track:** API
**Status:** DONE
**Execution Status:** MERGED (PR #166, commit a358be6)
**Priority:** P0

## Objective
Expose a complete, versioned recommendation detail and longitudinal history model so the Flutter app can explain not only the current prediction but how it changed and what happened afterward.

## Contracts
`GET /api/v1/recommendations/{id}` — current recommendation.

`GET /api/v1/recommendations/{id}/history?from=&to=&cursor=` — prediction revisions and daily tracking snapshots.

`GET /api/v1/recommendations/{id}/events?cursor=` — material news/events/reanalysis triggers.

`GET /api/v1/recommendations/{id}/outcome` — target/SL/horizon outcome and evidence.

## Detail Response
`id, symbol, exchange, companyName, predictionVersion, createdAt, updatedAt, asOf, entryPrice, currentPrice, targetPrice, stopLoss, horizonDays, expiryAt, upsidePct, probability, score, confidence, trustScore, uncertainty, evidenceStrength, fundamental, technical, market, news, events, benchmarkRelative, liquidity, providerEvidence, status`

## History Item
`timestamp, version, price, targetPrice, stopLoss, probability, score, confidence, trustScore, triggerType, triggerEventId, changeSummary`

## Outcome
`status, detectedAt, observedPrice, realizedReturnPct, targetHit, stopLossHit, horizonExpired, benchmarkReturnPct, evidenceId`

## Acceptance Criteria
- Historical versions are immutable.
- Current detail is never reconstructed by mutating history.
- History can explain every material revision.
- Outcome data includes exact detection evidence.
- Pagination and date filtering are stable.
- API does not expose internal negative/cautious recommendation categories as user-facing recommendations.

## Parallelization
API implementation. UI EPIC-141 must consume these contracts exactly.

## Dependencies
EPIC-135, EPIC-105, EPIC-122, EPIC-129, EPIC-132.

**Dependency note (2026-08-21):** EPIC-135 is `DONE`. EPIC-105 (freshness/
revision engine), EPIC-122 (real-time outcome monitor), EPIC-129 (information
latency) and EPIC-132 (benchmark-relative alpha) are all still `APPROVED`/
not implemented. None of them gate this EPIC's actual scope, since the
underlying capabilities they'd eventually feed already exist from earlier
merged EPICs: EPIC-050's `app.recommendation_revision` already provides a
real, immutable revision chain (`/history`'s primary content); EPIC-005's
`PredictionOutcome` already provides real (if not sub-second-real-time)
outcome detection (`/outcome`); EPIC-029/EPIC-078's evidence/liquidity
classifiers already exist. Named, honest gaps until each lands:
`benchmarkRelative`/`benchmarkReturnPct` are always `None` (no benchmark
module exists at all yet -- EPIC-132), outcome detection reflects
periodic/lifecycle-check-time evaluation rather than true real-time
latency (EPIC-122), and `expiryAt` is a naive calendar-day estimate rather
than trading-day/market-calendar-aware (EPIC-124, not even in this EPIC's
own dependency list, would be needed for that).

## Completion Report (2026-08-21)

**Implemented**, composing existing, already-merged domain modules:
- `GET /api/v1/recommendations/{id}` — resolves the `RecommendationGeneration` by id, then EPIC-050's `get_active_version` to show the **current** (possibly revised) prediction, never the stale original, per AC "current detail is never reconstructed by mutating history." Fields sourced from: EPIC-042 publication (target/stop/upside, falling back to raw prediction fields if unpublished), EPIC-138's shared `context_summaries` module (fundamental/news/events/market — refactored out of `api/services/recommendations.py` into `api/services/context_summaries.py` so both endpoints share one implementation instead of two), EPIC-029's `classify_liquidity_bucket` (liquidity), EPIC-019/EPIC-078 (uncertainty/evidenceStrength), EPIC-061's `RecommendationDecisionTrace.evidence_categories_snapshot` (providerEvidence).
- `GET /api/v1/recommendations/{id}/history?from=&to=&cursor=` — every entry in EPIC-050's immutable revision chain, each carrying its own revised prediction's price/target/stop/probability/confidence plus best-effort score/trust, `triggerType`=`revision_reason`, `triggerEventId`=the triggering `EvidenceRevalidationCheck` id, and a `changeSummary` built from EPIC-050's own `compare_versions` deltas (never re-derived). Date-filterable (`from`/`to`), offset-cursor paginated (see below).
- `GET /api/v1/recommendations/{id}/events?cursor=` — merges EPIC-090's `NewsEventRecord`, `CorporateAction`, and EPIC-049's `EvidenceRevalidationCheck` (`revalidation_required=True`, as the "reanalysis trigger" category) for the recommendation's stock into one chronological, typed (`NEWS`/`CORPORATE_ACTION`/`REANALYSIS_TRIGGER`) feed.
- `GET /api/v1/recommendations/{id}/outcome` — real evaluated outcome from EPIC-005's `PredictionOutcome` when it exists (`status`/`targetHit`/`stopLossHit`/`horizonExpired` derived honestly from the immutable record, `evidenceId` = the outcome row's own id, which **is** the auditable evidence — its `highest_price`/`lowest_price`/`closing_price` fields are the exact detection evidence per AC). Returns `status: "PENDING"` (not a 404) with every other field `null` when the prediction hasn't been evaluated yet — an honest, useful state rather than an opaque not-found.
- **Pagination**: `/history` and `/events` use a new, simpler `api/pagination.py::encode_offset_cursor`/`decode_offset_cursor` (opaque base64 offset) rather than EPIC-138's full keyset pagination — deliberately, since each is a small, effectively-immutable, single-recommendation-scoped sequence (not a large live-ranked feed), so "stable during a query session" (AC) holds without keyset machinery.
- A real, timezone bug found and fixed during testing: SQLite drops tzinfo on `DateTime(timezone=True)` round-trip (a documented gotcha for this repo), so a revision's `revised_at` can come back naive while the `from`/`to` query params (always offset-bearing) are aware — `get_history` now normalizes both sides to aware UTC (`_as_aware_utc`) before comparing.

**Tests:** `tests/test_api_recommendation_detail.py` (11 new tests) — 404 for a missing recommendation, full detail field shape, detail reflecting an active revision (not the stale original), history with a revision's change summary, empty history when never revised, date-range filtering, events merging news/corporate-actions/reanalysis-triggers in descending order, events cursor pagination covering every item exactly once, outcome `PENDING` before evaluation, and outcome reflecting a real `evaluate_recommendation` result.

**Validation run:**
```
DATABASE_URL="postgresql+psycopg://ci:ci@localhost/market_agent" python -m pytest -q
# 991 passed, 6 skipped -- full existing suite plus the 11 new tests, no regressions.
```

**Explicitly deferred (named, not fabricated):** benchmark-relative fields (EPIC-132); true real-time outcome-detection latency (EPIC-122); trading-day/market-calendar-aware `expiryAt` (EPIC-124, not even a stated dependency of this EPIC).
