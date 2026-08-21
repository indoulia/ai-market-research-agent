# EPIC-M1.129 — Multi-Level Benchmark-Relative Opportunity Intelligence

**Status:** VALIDATING
**Execution Status:** IMPLEMENTED_PENDING_MERGE
**Priority:** P1

## Objective
Determine whether a recommendation creates genuine stock-specific value relative to its industry, sector and broad-market benchmarks rather than simply benefiting from a rising market.

## Scope
- Compare stock performance with industry, sector and broad-market benchmarks.
- Calculate benchmark-relative return and alpha-like measures using appropriate methodology.
- Evaluate target/SL outcomes relative to benchmark behavior over the same horizon.
- Preserve benchmark membership and methodology versions.
- Segment prediction quality by benchmark-relative environment.
- Feed relative opportunity into ranking and usefulness measurement.

## Acceptance Criteria
- Every eligible closed recommendation can be evaluated against relevant benchmarks.
- Benchmark comparisons use point-in-time appropriate benchmark membership/data.
- Raw stock return and relative performance remain separate metrics.
- Ranking can prefer genuine relative opportunities according to policy.
- Historical benchmark methodology is reproducible.

## Dependencies
M1.86, M1.98, M1.99, M1.109.

## Completion Report

**Status:** implemented on branch `autonomous/epic-m1-129`, PR opened against `main`, not yet merged.

**Implementation:**
- `app/benchmark_relative_alpha.py`: new, versioned (`BENCHMARK_RELATIVE_VERSION = "BRA-001"`) module.
- **New data, not fabricated:** no index/benchmark price series existed on this platform before this EPIC (`Stock`/`MarketPrice` model only equities). Two new tables (migration `0099_benchmark_relative_alpha.py`): `benchmarks` (a small registry -- code/level/label/symbol/sector) and `benchmark_daily_prices` (close by benchmark+trade_date). Prices are ingested through this platform's existing `market_data.yahoo.YahooFinanceClient.fetch_daily_candles` -- it is symbol-generic, so an index ticker (`^NSEI` for the broad market) flows through the same call used for equities, not a new vendor integration (`ingest_benchmark_daily_history`).
- **Compare stock performance with industry, sector and broad-market benchmarks:** `assess_benchmark_relative_opportunity` always evaluates `BROAD_MARKET` (`^NSEI`, Nifty 50) and additionally `SECTOR` when `Stock.sector` is one of the fixed, documented entries in `SECTOR_BENCHMARK_SYMBOLS` (IT, Banking/Financial Services, Pharma, Auto, FMCG, Metal, Energy, Realty -- by their real NSE sector-index tickers). **Industry-level benchmarking is honestly out of scope for this first version** -- this platform has no curated industry-index mapping, the same posture M1.109 already took for peer valuation/fundamentals; named here rather than fabricated. An unmapped sector, or a benchmark with no price data covering the relevant dates, yields `INSUFFICIENT_BENCHMARK_DATA` rather than a guessed number.
- **Benchmark-relative return / alpha-like measure:** `relative_alpha = stock_return_pct - benchmark_return_pct`, where `stock_return_pct` is `PredictionOutcome.actual_return` (M1.5) read verbatim -- never recomputed -- and `benchmark_return_pct` is the benchmark's own return over the identical `entry_date` (`Prediction.as_of_timestamp.date()`) to `evaluation_date` (`PredictionOutcome.evaluation_date.date()`) window, using a strictly point-in-time (`<=` target date, most recent) benchmark price lookup on each end -- never a later, unavailable price. Verdicts: `GENUINE_RELATIVE_OPPORTUNITY` (alpha >= +1pp), `UNDERPERFORMED_BENCHMARK` (alpha <= -1pp), `MARKET_DRIVEN` (within the 1pp band either side), `INSUFFICIENT_BENCHMARK_DATA`.
- **Raw stock return and relative performance remain separate metrics** (acceptance criteria): `stock_return_pct` and `benchmark_return_pct`/`relative_alpha` are distinct columns on `BenchmarkRelativeAssessment`, never merged into one number.
- **Evaluate target/SL outcomes relative to benchmark behavior over the same horizon:** satisfied by comparing `outcome.actual_return` -- the same value that already determined `target_hit`/`stop_hit` -- against the benchmark's return over that identical horizon window; a finer-grained, day-by-day trace of exactly when the target/stop triggered relative to the benchmark is out of scope, since `PredictionOutcome` itself carries no intra-horizon timestamp to begin with.
- **Preserve benchmark membership and methodology versions:** each assessment row freezes `benchmark_id`/`benchmark_code` and `assessment_rule_version` at `evaluated_at` -- if `SECTOR_BENCHMARK_SYMBOLS` is revised in a later version, historical assessments are unaffected, the same frozen-row posture M1.109's `SectorRelativeAssessment` already established.
- **Segment prediction quality by benchmark-relative environment:** `compare_benchmark_relative_performance` reuses `trust_report`'s `VERDICT_OK`/`VERDICT_WEAK`/`VERDICT_INSUFFICIENT_SAMPLE` vocabulary and `MIN_SAMPLE_SIZE_FOR_COMPARISON`/`WEAKNESS_MARGIN`, comparing a benchmark-relative-environment segment's success rate against the platform-wide baseline within a window -- the same always-fresh "report" posture as M1.85/M1.99/M1.102/M1.108/M1.109.
- **Feed relative opportunity into ranking and usefulness measurement:** propose-only -- no write path to `Prediction`, `PositiveOpportunityRanking`, `PredictionUsefulnessAssessment`, or any ranking/Trust Score table, the same posture M1.109/M1.122/M1.130 already established. Documented here as explicit future work, not fabricated.
- **API wiring (read-only, no new computation triggered from a request):** `api/services/recommendation_detail.py` (M1.137) and `api/services/tracking.py` (M1.147) both explicitly stubbed `benchmarkRelative`/`benchmarkReturnPct`/`benchmarkReturn`/`relativeReturn` as `None` pending this EPIC. Both now read the latest already-computed `BROAD_MARKET`-level `BenchmarkRelativeAssessment` row(s) when present (`recommendation_detail.get_detail`/`get_outcome`: the single prediction's own assessment; `tracking.get_summary`: the average across the window's closed, genuine predictions that have one) -- `None` continues whenever no assessment has actually been computed yet, since neither module invokes the assessment function itself.

**Tests:** `tests/test_benchmark_relative_alpha.py` (11 tests) -- insufficient-benchmark-data with no price data, genuine/market-driven/underperformed verdicts (alpha math verified by hand), sector-level assessment present only for a mapped sector and absent for an unmapped one, no-outcome-yet returns no assessments, idempotency, point-in-time price lookup falling back to the nearest prior trade date, benchmark-performance-report insufficient-sample/ok cases, and idempotent benchmark price ingestion via a fake `fetch_daily_candles` client. Existing `tests/test_api_recommendation_detail.py`/`tests/test_api_tracking.py` assertions that `benchmarkRelative`/`benchmarkReturn` are `None` still hold (their fixtures never compute an assessment) -- only the stale "M1.129 not implemented" comment was corrected.

**Rebase note:** this branch was rebased twice while M1.118, then M1.125, landed on `main` mid-flight. M1.118's migration first collided with this EPIC's `0097` number; while resolving it, running the full suite against a real local Postgres (not sqlite) surfaced a genuine, pre-existing defect in M1.118's own migration, unrelated to this EPIC: its revision id `"0097_event_schedule_orchestration"` was 33 characters, one over Postgres's default `alembic_version.version_num VARCHAR(32)`, so `alembic upgrade head` fails with `StringDataRightTruncation` on a real Postgres. This went uncaught in CI because CI provisions no Postgres service (`tests/test_fresh_database_migration.py` explicitly skips without one). A peer (`market-agent-m1-91`) independently reported and fixed the same bug upstream (PR #231, renamed to `0097_event_sched_orchestration`) before this branch's own duplicate fix was pushed, so this branch rebased onto that fix instead of duplicating it. M1.125 then claimed `0098`, so this EPIC's migration is renumbered a final time to `0099_benchmark_relative_alpha.py`.

**Verification (real commands run, not fabricated):**
- `python -m pytest tests/test_benchmark_relative_alpha.py -q` -> `11 passed`
- `python -m pytest tests/test_api_recommendation_detail.py tests/test_api_tracking.py -q` -> `24 passed`
- `python -m pytest -q` (full suite, real local Postgres) -> `1224 passed` (grew from 1182 as `main` advanced through M1.118/M1.125 during the rebase)
- `python -m alembic heads` -> single head `0099_benchmark_relative (head)`, chain resolves cleanly
