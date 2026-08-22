# EPIC-150 — Longitudinal Tracking & Performance Analytics API

**Track:** API
**Status:** DONE
**Execution Status:** MERGED (PR #208, commit fcc4a3b)
**Priority:** P0

## Objective
Expose historical recommendation and model performance in a compact analytical contract so users can see whether MRA is improving over time.

## Contracts
`GET /api/v1/tracking/summary?range=7d|30d|90d|1y`

Response: `predictionCount,closedCount,targetHitRate,stopLossRate,horizonExpiryRate,avgRealizedReturn,avgPredictedReturn,calibrationScore,trustScore,trustDelta,modelVersion,benchmarkReturn,relativeReturn`.

`GET /api/v1/tracking/timeseries?metric=trust|hitRate|return|calibration&range=&bucket=day|week`

`GET /api/v1/tracking/breakdown?dimension=horizon|sector|marketCap|regime|setup`

`GET /api/v1/tracking/predictions?status=active|closed&cursor=`

## Rules
- Metrics are calculated from immutable outcome history.
- Closed prediction counts and denominators are explicit.
- Small samples are flagged rather than presented as authoritative.
- Benchmark-relative results are separate from raw returns.
- Trust is displayed with evidence/sample context.

## Acceptance Criteria
- API can render a historical Trust Score series.
- API can show outcome performance over selectable periods.
- API supports horizon/sector/regime breakdowns.
- Metrics are reproducible and versioned.
- No metric silently mixes prediction versions or incomplete outcomes.

## Parallelization
API analytics team.

## Dependencies
EPIC-119, EPIC-120, EPIC-122, EPIC-125, EPIC-132.

**Dependency note (2026-08-21):** EPIC-119 is `DONE`; EPIC-120 has a `DONE`
duplicate doc (`EPIC-120-prediction-quality-monitoring-trust-dashboard.md`)
alongside its unapproved sibling -- the completed one's `PredictionTrustScore`/
trust-dashboard machinery is what this EPIC actually reads. EPIC-122
(real-time outcome monitor), EPIC-125 (statistical reliability/
uncertainty) and EPIC-132 (benchmark-relative alpha) are still `APPROVED`/
not implemented. None of this EPIC's four contracts need them to exist:
`PredictionOutcome`/`PredictionTrustScore`/`ConfidenceCalibrationRecord`
already provide real, immutable historical evidence. Named, honest gaps
until each lands: `benchmarkReturn`/`relativeReturn` are always `None`
(EPIC-132); rates/averages are point-in-time, not confidence-interval or
significance-tested claims (EPIC-125); analytics reflect whatever's
already evaluated, not real-time push updates (EPIC-122).

## Completion Report (2026-08-21)

**Implemented**, composing existing, already-merged domain modules --
nothing recomputed:
- `GET /api/v1/tracking/summary?range=7d|30d|90d|1y` — real counts/rates from EPIC-005's `PredictionOutcome` (target/stop/expiry rates, realized vs. predicted return), EPIC-080's `PredictionTrustScore` (latest per prediction, plus a genuine period-over-period `trustDelta` against the prior equal-length window), and EPIC-072's `ConfidenceCalibrationRecord.calibration_error` for `calibrationScore` (average error magnitude; lower is better). `modelVersion` reports `"MIXED"` honestly rather than picking one arbitrarily when the range spans more than one model version (AC: "no metric silently mixes prediction versions"). `smallSample` (new field, not in the original doc's field list but required by this EPIC's own AC "small samples are flagged rather than presented as authoritative") reuses the platform's existing `MIN_SAMPLE_SIZE_FOR_COMPARISON=20` threshold (EPIC-099's own comparison-validity floor) rather than inventing a new one.
- `GET /api/v1/tracking/timeseries?metric=trust|hitRate|return|calibration&range=&bucket=day|week` — buckets genuine predictions (real `RecommendationGeneration` link) by their `as_of_timestamp` into day/week buckets and computes the requested metric per bucket, with an honest `sampleCount` alongside every point.
- `GET /api/v1/tracking/breakdown?dimension=horizon|sector|marketCap|regime|setup` — real grouping by horizon days, `Stock.sector`, `classify_market_cap_bucket` (EPIC-029, same canonical thresholds EPIC-138/139 already reuse), and market regime (via the recommendation's originating scan). `setup` — no strategy/pattern-type classification module exists anywhere in this platform — returns a single, honest `UNCLASSIFIED` bucket rather than a fabricated taxonomy.
- `GET /api/v1/tracking/predictions?status=active|closed&cursor=` — real keyset-paginated list of genuine predictions, split by whether a `PredictionOutcome` exists yet.
- Only predictions with a real `RecommendationGeneration` link are counted anywhere in this EPIC (the provenance-link pattern EPIC-097/98 established), so a revision's follow-on prediction is attributed to its original, matching how EPIC-138/137 identify recommendations.
- A real SQLite tzinfo round-trip bug (the same class already fixed in EPIC-140) found and fixed in `/timeseries`'s day/week bucketing arithmetic.
- `bootstrap.capabilities.analytics` flipped to `true`.

**Tests:** `tests/test_api_tracking.py` (11 new tests) — empty summary state, invalid range rejection, real counts/rates/trust/model-version over a closed prediction (plus the new `smallSample` flag), invalid metric rejection, day-bucketed timeseries with a correct sample count and average, horizon breakdown, the honest single-bucket `setup` dimension, invalid dimension rejection, active/closed status filtering (including a real `outcome` value), missing-status rejection, and cursor pagination covering every prediction exactly once. Plus 1 updated assertion in `tests/test_api_contract.py`.

**Validation run:**
```
DATABASE_URL="postgresql+psycopg://ci:ci@localhost/market_agent" python -m pytest -q
# 1106 passed, 6 skipped -- full existing suite plus the 11 new tests, no regressions.
```

**Migration note:** this EPIC needed no new table -- it is purely a read-side aggregation over existing immutable evidence.

**Explicitly deferred (named, not fabricated):** benchmark-relative fields (EPIC-132); statistical significance/confidence intervals on any rate (EPIC-125, `smallSample` is a floor-based flag, not a confidence interval); true real-time analytics push (EPIC-122); a `setup`/strategy-pattern breakdown taxonomy (no such classification module exists in this platform at all).
