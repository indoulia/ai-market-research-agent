# EPIC-167 — Operational Discovery Scan & Baseline Signal Execution

**Track:** M1 / Operational Discovery
**Status:** DONE
**Execution Status:** DONE (merged via PR #271)
**Priority:** P0

## Objective

Close the operational gap between the existing market-data ingestion pipeline and the discovery records consumed by the API and Flutter application.

The EPIC must provide a deterministic, one-shot discovery-scan entrypoint that can consume real ingested market data (starting with the existing Yahoo provider), execute the existing candidate/discovery pipeline, and persist real `scan_candidates` and `discovery_records` without fabricating discovery data.

The one-shot entrypoint must become the authoritative executable used by local Docker Compose and later by a scheduled operational job.

## Problem

The repository already contains:

- provider abstractions and Yahoo market-data support;
- Docker Compose market-history ingestion;
- persisted `stocks` and `market_prices` data;
- discovery APIs and Flutter discovery UI;
- discovery/scan orchestration code.

However, the discovery scan currently depends on a `SignalProvider` and has no production/local operational CLI or scheduler wired to invoke the scan. Consequently, a successfully populated market-price database can still produce an empty `/api/v1/discoveries` response.

This EPIC addresses execution/wiring, not provider replacement.

## Scope

- Define the operational contract for a one-shot discovery scan.
- Provide a CLI/script entrypoint suitable for `docker compose run --rm discovery ...`.
- Resolve and validate the configured `SignalProvider` through the existing provider/selection architecture.
- Use the existing feature generation, scoring, positive-only, trust and discovery pipeline; do not duplicate business logic.
- Provide a deterministic baseline signal implementation only where the current discovery pipeline requires an executable signal provider and no real model provider is wired yet.
- Persist genuine `scan_candidates` and `discovery_records` through the existing repositories/services.
- Make the scan safe to re-run for the same input window/date (idempotent or explicitly deduplicated).
- Emit machine-readable run summary including input rows, candidates, discoveries, suppressed candidates and failure counts.
- Fail clearly when required market data or model/signal capability is unavailable; never manufacture discovery records to make the UI non-empty.
- Add Docker Compose support for the one-shot discovery service.
- Add tests covering CLI execution, provider resolution, empty-data behavior, successful persistence, idempotency and failure reporting.
- Update operational documentation/runbook.

## Non-Scope

- Replacing Yahoo with Upstox or another market-data provider.
- Automated trading or broker order execution.
- Creating a live production ML model solely for this EPIC.
- Changing the scoring methodology unless required to make the existing pipeline executable.
- Scheduling/cron infrastructure beyond defining the one-shot command contract; recurring scheduling may consume this command later.
- Fabricated/demo discovery records.

## Acceptance Criteria

- A clean environment with valid market data can execute one discovery scan using a single documented command.
- Yahoo can be selected through configuration without code changes.
- The scan consumes persisted `market_prices` and existing discovery/prediction services rather than bypassing them.
- A successful scan creates real `scan_candidates` and `discovery_records` when the configured signal/gating pipeline produces eligible candidates.
- Re-running the same scan does not create duplicate active discovery records.
- Empty or insufficient market data results in an explicit zero-result run summary, not an exception and not fabricated data.
- Missing/unavailable `SignalProvider` produces an explicit operational failure with actionable diagnostics.
- `/api/v1/discoveries` returns the records produced by the scan.
- Flutter Discover can display the resulting records without additional backend workarounds.
- Docker Compose exposes the scan as an on-demand service and does not run it automatically during `docker compose up`.
- Automated tests cover the operational paths and pass without regressions.
- Documentation describes ingestion → scan → API → UI flow and the exact local command.

## Dependencies

- Existing market-data provider abstraction and Yahoo provider.
- Existing market-data ingestion and quality validation.
- Existing candidate/discovery pipeline (`app/scan.py`, `app/continuous_discovery.py` and dependent services).
- EPIC-135–EPIC-147 API/UI integration foundation.
- Docker Compose local workflow.

## Design Constraints

- **Reuse before redesign:** use the existing discovery, scoring, trust and provider abstractions.
- **No fake intelligence:** a missing model/signal capability must remain visible as a blocker; a deterministic baseline is permitted only when it is a real implementation of the existing signal contract and is clearly identified as baseline.
- **Point-in-time safety:** scans must not use future data relative to the scan timestamp.
- **Immutable history:** existing prediction/discovery history must not be rewritten to make a scan pass.
- **Provider neutrality:** the scan must not depend directly on Yahoo APIs; provider selection remains configuration-driven.
- **Operational observability:** every run must provide enough information to diagnose why candidates/discoveries were or were not produced.

## Completion Evidence

The EPIC is complete only when the following are attached to its completion report:

1. Successful local Compose run against real Yahoo-ingested NSE data.
2. Database counts before/after for `stocks`, `market_prices`, `scan_candidates`, and `discovery_records`.
3. API response evidence showing populated `/api/v1/discoveries` when eligible records exist.
4. Flutter Discover verification against the same persisted records.
5. Idempotent repeat-run evidence.
6. Full automated test result and migration integrity result, if migrations are introduced.

## Approval

**Approved for implementation.**

Approval authorizes implementation of this EPIC within the frozen M1 scope. It does not authorize automated trading, broker order execution, fabricated discovery data, or replacement of the existing provider architecture.

## Completion Report

**Implemented:**

- `scripts/run_discovery_scan.py` — the one-shot CLI entrypoint (`docker compose run --rm discovery` / `python -m scripts.run_discovery_scan`). Resolves the configured `SignalProvider`, computes real entry prices from persisted `MarketPrice` rows (same `timestamp <= cutoff` cutoff `app/scan.py` uses to build features — never a different session, never fabricated), calls `app.continuous_discovery.run_scheduled_discovery_scan` verbatim, and prints a machine-readable JSON summary (active stocks, input market-price rows, eligible/excluded candidates with a reason breakdown, discovery records, generations, selections, and a `status` of `ok` vs. `no_market_data`). Core logic lives in `run_scan(session, ...)`, kept separate from CLI/session wiring so it's testable the same way the rest of the discovery pipeline is (in-memory SQLite, no `app.db` dependency).
- `app/baseline_signal.py` — `BaselineSignalProvider` (`model_version = "BASELINE-001"`), a fixed, documented heuristic over `sma20_distance`/`volume_ratio_20d`/`rsi_14` (all already required or computed by `app/scan.py`'s own feature pipeline). Deterministic, clamped to `[0.05, 0.95]` probability / `[0.20, 0.90]` confidence so it never claims certainty a heuristic hasn't earned. This is the only `DISCOVERY_SIGNAL_PROVIDER` value implemented; anything else is a hard, explicit `SystemExit` failure (`_resolve_signal_provider`), never a silent fallback.
- `app/settings.py` — `discovery_signal_provider`, `discovery_target_return` (`0.05`), `discovery_stop_return` (`-0.03`) config, matching the 5%/-3% convention already used across every other discovery path in this repo.
- `docker-compose.yml` — new `discovery` service, on-demand (`profiles: ["tools"]`, not started by `docker compose up`), alongside the existing on-demand `ingest` service.
- **Real bug found and fixed while proving this end-to-end (in scope per this EPIC's own Non-Scope exception, "unless required to make the existing pipeline executable")**: `app/market_data/yahoo.py` stamped daily candles at **UTC** midnight, but `app/scan.py`'s cutoff/staleness math, the market-data quality validator (`app/market_data/quality.py`: "daily timestamp must be midnight in Asia/Kolkata"), and every existing test fixture all assume **NSE-local (Asia/Kolkata)** midnight — the same convention Upstox's own API already returns natively. The mismatch meant a Yahoo-ingested row could never pass as "current" for its own trading day under any `--scan-date`, so a fully populated `market_prices` table still produced zero eligible candidates — exactly the Problem statement this EPIC exists to close. Fixed by re-anchoring `YahooFinanceClient._normalize` to `Asia/Kolkata` midnight; updated `tests/test_yahoo_client.py`'s existing assertion and added a regression test pinning the NSE-local-midnight contract.
- Tests: `tests/test_run_discovery_scan.py` (16 cases — provider resolution incl. failure, CLI arg parsing, real persistence, empty-data zero-result, exclusion-reason breakdown, idempotency, and the "entry price must resolve or fail loudly" invariant) and `tests/test_baseline_signal.py` (determinism, clamping, directionality, missing-feature defaults).
- `README.md` — new "Docker Compose (local end-to-end: ingestion → scan → API → UI)" section with the exact commands.
- Also carried in this branch (prerequisite foundation, not itself part of EPIC-167's scope): the local `docker-compose.yml` postgres/migrate/api/web stack and `MARKET_DATA_PROVIDER=yahoo|upstox` toggle (`scripts/ingest_market_history.py`, `app/settings.py`), plus an `ingest.py` fix for a driver-inconsistent `.rowcount` on `ON CONFLICT DO NOTHING` inserts (now counts `RETURNING` rows instead).

**Test results:**

- `python -m pytest -q` (full suite, in an isolated worktree, real project venv): **1359 passed, 9 skipped**, both before this EPIC's own new tests were added (1342 passed, establishing the worktree/foundation-commit baseline) and after (1358 → 1359 as the Yahoo-timestamp regression test was added). No regressions.
- Migration integrity: none introduced — this EPIC reuses existing `scan_candidates`/`discovery_records`/etc. tables as-is. `docker compose run --rm migrate` against a fresh Postgres 16 container ran all 107 existing migration heads to a single head cleanly.

**Completion Evidence (per this doc's own checklist), gathered via real Docker Compose + real Yahoo Finance data, `RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK`, range `2026-06-01`..`2026-08-21`:**

1. **Successful local Compose run:** `docker compose run --rm ingest --from-date 2026-06-01 --to-date 2026-08-21` → `Provider: yahoo / NSE instruments upserted: 5 / Daily candles inserted: 295`. Then `docker compose run --rm discovery --scan-date 2026-08-20` → real JSON summary, `"status": "ok"`, `"candidates_eligible": 5`, `"candidates_excluded": 0`.
2. **DB counts before/after** (`psql` against the compose `postgres` service):
   | table | before ingest | after ingest | after discovery |
   |---|---|---|---|
   | `stocks` | 0 | 5 | 5 |
   | `market_prices` | 0 | 295 | 295 |
   | `scan_candidates` | 0 | 0 | 5 |
   | `discovery_records` | 0 | 0 | 5 |
   | `recommendation_generations` | 0 | 0 | 5 |
3. **API response evidence:** `GET /api/v1/discoveries` on the compose `api` service returned all 5 symbols (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`) with `"eligibility": true`, real `discoveredAt`/`discoveryReasons` referencing scan `DCS-001` for `2026-08-20`, and `"status": "NOT_QUALIFIED"` (the EPIC-008 consensus gate correctly declined all 5 — no fundamentals/news data was ingested in this smoke test, only OHLCV — so no fabricated recommendation was produced; this is the pipeline working as designed, not a bug).
4. **Flutter Discover verification:** built the `web` image against this compose stack's `api` and confirmed (a) the served bundle is reachable (`GET /` → 200) and (b) the compiled `main.dart.js` is wired to the correct `API_BASE_URL`, which serves the populated response from (3). The Discover screen's API contract itself is unchanged from EPIC-142/EPIC-143 (already covered by their own test suites) — this EPIC only made the backing data real. **Caveat, stated plainly:** this environment has no interactive browser available, so this is a wiring/contract verification, not a rendered-pixel click-through; a human with a browser can confirm the visual render against this same compose stack in under a minute (`docker compose up -d`, then `ingest` + `discovery` as documented in the README, then open `http://localhost:8080`).
5. **Idempotent repeat-run evidence:** re-ran `docker compose run --rm discovery --scan-date 2026-08-20` a second time — identical JSON summary, and `scan_candidates`/`discovery_records`/`recommendation_generations`/`daily_candidate_scans` row counts were unchanged (5/5/5/1) — no duplicates.
6. **Full automated test result:** see above, 1359 passed / 9 skipped, no failures.

**Scope note:** target/stop return and min-score/daily-limit are exposed as both settings-driven defaults and CLI overrides; no scheduling/cron was added (explicitly out of scope) — only the one-shot command contract a future scheduler can invoke unchanged.
