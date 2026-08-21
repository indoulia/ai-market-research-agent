# EPIC-M1.149 — Operational Discovery Scan & Baseline Signal Execution

**Track:** M1 / Operational Discovery
**Status:** APPROVED
**Execution Status:** NOT STARTED
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
- M1.132–M1.144 API/UI integration foundation.
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
