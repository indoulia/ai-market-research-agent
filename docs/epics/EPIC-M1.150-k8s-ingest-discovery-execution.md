# EPIC-M1.150 — Kubernetes-Native Ingest & Discovery-Scan Execution

**Track:** M1 / Operational Discovery
**Status:** VALIDATING
**Execution Status:** IMPLEMENTED, PR OPEN
**Priority:** P1

## Objective

Close the same operational gap EPIC-M1.149 closed for Docker Compose, but for the
Rancher Desktop (k3s) deployment: give the Kubernetes deployment a documented,
repeatable way to run market-data ingestion and the discovery scan against the
in-cluster PostgreSQL, so a deployed cluster's `/api/v1/discoveries` and Flutter
Discover screen are populated the same way the Compose workflow already is.

## Problem

EPIC-M1.149 added `scripts/ingest_market_history.py` and
`scripts/run_discovery_scan.py`, wired as on-demand `docker compose run --rm ingest`
/ `discovery` services. The Kubernetes manifests under `deploy/k8s/base/` have no
equivalent: only `namespace`, `postgres`, `api-deployment`, `web-deployment`,
`ingress`, and a one-shot `migration-job`. A freshly deployed cluster's Postgres has
zero rows in `stocks`/`market_prices`/`scan_candidates`/`discovery_records` — the API
and Flutter UI are both honestly empty, with no documented in-cluster command to fix
that. The only way to populate a cluster today is to hand-write a throwaway `Job`
manifest, which is what happened while diagnosing why the Discover screen showed
nothing on `market-agent.test`.

Additionally, `deploy/k8s/market-agent.env.example` (the source of the
`market-agent-secrets` Secret) has no `MARKET_DATA_PROVIDER` / `YAHOO_SYMBOLS` keys,
so even a correctly-authored ingest Job has nothing to configure the provider from
without editing a manifest directly.

## Scope

- Add `deploy/k8s/base/ingest-job.yaml`: an on-demand `Job` (same pattern as
  `migration-job.yaml`) running `scripts.ingest_market_history`, with the date range
  and provider selection driven by env vars (`FROM_DATE`/`TO_DATE`, defaulted to a
  sensible recent window; `MARKET_DATA_PROVIDER`/`YAHOO_SYMBOLS`/`UPSTOX_*` from the
  existing `market-agent-secrets` Secret).
- Add `deploy/k8s/base/discovery-job.yaml`: an on-demand `Job` for a single manual
  `scripts.run_discovery_scan` invocation, mirroring `docker compose run --rm discovery`.
- Add `deploy/k8s/base/discovery-cronjob.yaml`: a `CronJob` running the same discovery
  scan on a documented daily schedule, so a long-running cluster doesn't depend on
  someone remembering to trigger it manually after each ingest.
- Add `MARKET_DATA_PROVIDER`, `YAHOO_SYMBOLS` (and document the already-defaulted
  `DISCOVERY_SIGNAL_PROVIDER`) to `deploy/k8s/market-agent.env.example`.
- Wire the new Jobs/CronJob into `deploy/k8s/deploy.ps1` and `deploy/k8s/README.md`
  so the full ingestion → scan → API → UI flow is a documented, one-command-per-step
  operation, matching the root `README.md`'s Docker Compose section.
- Reuse `scripts/ingest_market_history.py` and `scripts/run_discovery_scan.py`
  verbatim; no business-logic changes.

## Non-Scope

- Changing the discovery/scoring/signal-provider logic itself (EPIC-M1.149's scope).
- Production-grade scheduling policy: alerting on Job/CronJob failure, retry/backoff
  tuning beyond Kubernetes defaults, multi-cluster or multi-environment scheduling.
- Replacing the Docker Compose workflow; both remain supported, independent paths.
- A real market-data provider swap (still Yahoo-by-default, Upstox-ready via config).
- Fabricated/demo discovery records under any circumstance.

## Acceptance Criteria

- `kubectl apply -f deploy/k8s/base/ingest-job.yaml` (deleted/reapplied per run, same
  pattern as `migration-job.yaml`) ingests real market data into the cluster's own
  PostgreSQL using whichever provider `MARKET_DATA_PROVIDER` selects.
- `kubectl apply -f deploy/k8s/base/discovery-job.yaml` (or the `CronJob` firing on
  schedule) turns already-ingested data into real `scan_candidates` and
  `discovery_records` via the existing pipeline, without fabricating data.
- Re-running either Job for the same window/date does not create duplicate records
  (inherits the existing scripts' idempotency; no new dedup logic needed).
- `GET /api/v1/discoveries` through the Traefik ingress (`market-agent.test`)
  reflects the persisted records.
- The Flutter Discover screen served by `web` displays the resulting records.
- `deploy/k8s/README.md` documents the exact commands for ingest, on-demand
  discovery, and the scheduled `CronJob`, mirroring the root README's Compose section.
- `kubectl apply -k deploy/k8s/base` still does not run ingestion or a one-shot
  discovery scan automatically (Jobs stay out of the kustomization's applied-on-every-
  deploy path — same reasoning as `migration-job.yaml` being applied separately); the
  `CronJob` itself is a standing/idle resource until its schedule fires, matching
  Compose's `ingest`/`discovery` never running on `docker compose up`.

## Dependencies

- EPIC-M1.149 (`scripts/ingest_market_history.py`, `scripts/run_discovery_scan.py`,
  their env/config contract) — merged into `main`.
- Existing Rancher Desktop (k3s) deployment (`deploy/k8s/`, PR #251).

## Design Constraints

- **Reuse before redesign:** the Jobs/CronJob invoke the existing scripts verbatim;
  no duplicated ingestion/discovery logic in Kubernetes-specific code.
- **No fake intelligence / no fabricated data:** identical to EPIC-M1.149 — empty or
  stale market data must surface as an honest empty/excluded result, never a
  manufactured discovery record.
- **Configuration-driven:** provider selection and credentials come from the existing
  `market-agent-secrets` Secret / `market-agent.env`, never hardcoded into a manifest.
- **Operational parity with Compose:** anyone who understands the Compose `ingest`/
  `discovery` workflow should be able to map it directly onto the Kubernetes one.

## Completion Evidence

The EPIC is complete only when the following are attached to its completion report:

1. `kubectl apply -f deploy/k8s/base/ingest-job.yaml` run against the real Rancher
   Desktop cluster, with the resulting row counts for `stocks`/`market_prices`.
2. `kubectl apply -f deploy/k8s/base/discovery-job.yaml` (or a CronJob-triggered run)
   against the same cluster, with resulting `scan_candidates`/`discovery_records`
   counts.
3. `GET /api/v1/discoveries` response (via the ingress) showing the resulting records.
4. A screenshot or equivalent evidence of the Flutter Discover screen at
   `market-agent.test` rendering those records.
5. Confirmation that re-running the ingest/discovery Job does not duplicate rows.

## Approval

**Approved for implementation.**

Approval authorizes implementation of this EPIC within the frozen M1 scope. It does
not authorize automated trading, broker order execution, fabricated discovery data,
or replacement of the existing provider architecture.

## Completion Report

**Implemented:**

- `deploy/k8s/base/ingest-job.yaml` — on-demand `Job` running
  `scripts.ingest_market_history`, date window via `FROM_DATE`/`TO_DATE` env
  (defaulted), provider/credentials via optional `secretKeyRef`s.
- `deploy/k8s/base/discovery-job.yaml` — on-demand `Job` running
  `scripts.run_discovery_scan`.
- `deploy/k8s/base/discovery-cronjob.yaml` — `CronJob`, schedule `30 10 * * 1-5`
  (10:30 UTC / 16:00 IST weekdays), added to `kustomization.yaml` so it's applied
  automatically (it only *schedules*; it never runs ingestion).
- `deploy/k8s/market-agent.env.example` — added `MARKET_DATA_PROVIDER`,
  `YAHOO_SYMBOLS`, documented already-defaulted `DISCOVERY_SIGNAL_PROVIDER`.
- `deploy/k8s/deploy.ps1` — added `-RunIngest` / `-RunDiscovery` switches.
- `deploy/k8s/README.md` — new "Ingest market data and run the discovery scan"
  section documenting the exact commands, mirroring the root README's Compose
  section.

**Tested against the real local Rancher Desktop (k3s) cluster** (`market-agent`
namespace, ingress host `market-agent.test`), not just read for correctness:

1. Rebuilt `market-agent-api:local` (the previously-loaded image predated this
   session's code and lacked `scripts/`), applied `kubectl apply -k deploy/k8s/base`
   — `cronjob.batch/market-agent-discovery created`, confirmed idle
   (`kubectl get cronjob`: `ACTIVE 0`, `LAST SCHEDULE <none>`).
2. Added `MARKET_DATA_PROVIDER`/`YAHOO_SYMBOLS` to the real (gitignored)
   `deploy/k8s/market-agent.env` and recreated the Secret.
3. `kubectl apply -f deploy/k8s/base/ingest-job.yaml` →
   `Provider: yahoo / NSE instruments upserted: 5 / Daily candles inserted: 0`
   (re-run of already-ingested data — 800 rows persisted from a prior run in the
   same investigation — correctly reported 0 new inserts, no duplication).
4. `kubectl apply -f deploy/k8s/base/discovery-job.yaml` →
   `input_market_price_rows: 800, candidates_eligible: 0,
   candidates_excluded_by_reason: {"stale_market_data": 5},
   discovery_records_created: 5, status: "ok"`.
5. DB counts before/after the re-run stayed at `discovery_records: 5`,
   `scan_candidates: 5`, `daily_candidate_scans: 1` — confirmed idempotent for the
   same scan date.
6. `curl -H "Host: market-agent.test" http://<traefik-ip>/api/v1/discoveries`
   returned all 5 records (`PENDING_ANALYSIS`, `eligibility: false` — honest,
   matching the stale-data exclusion above).
7. Headless-browser pass (Playwright) against `http://market-agent.test/discover`
   after signing in: all 5 stock cards render (ICICIBANK, HDFCBANK, INFY, TCS,
   RELIANCE), each showing "PENDING ANALYSIS" / "Not eligible" — screenshot
   confirmed visually, no console errors.

**Known follow-up (out of this EPIC's scope):** all 5 candidates are excluded as
`stale_market_data` with the current Jan–Aug 2026 Yahoo backfill window; nothing
will show real scores/recommendations in this cluster until the ingest window is
refreshed closer to the scan date.
