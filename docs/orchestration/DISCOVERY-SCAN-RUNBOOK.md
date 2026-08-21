# Discovery Scan Runbook

## Purpose

M1.149 provides a one-shot operational command that connects persisted market
history to the existing candidate/discovery pipeline. It is the executable
contract for local Docker Compose and future scheduling.

## Prerequisites

1. Database migrations are current.
2. At least one active NSE `Stock` exists.
3. `MarketPrice` contains persisted market history for the intended scan date.
4. The environment provides a valid `DATABASE_URL`.

## Run

```bash
python scripts/run_discovery_scan.py --scan-date 2026-08-21
```

If `--scan-date` is omitted, the command uses the latest persisted market
session. The default signal provider is `baseline-technical-v1`, an explicit
deterministic technical baseline used to exercise the real SignalProvider
contract until a trained production provider is wired.

The command does not fabricate discovery rows. Missing market data produces a
zero-result summary; a missing provider must fail rather than create synthetic
recommendations.

## Expected flow

```text
market-data ingestion
  -> stocks / market_prices
  -> run_discovery_scan.py
  -> run_daily_candidate_scan
  -> discovery provenance
  -> recommendation generation / selection
  -> discovery_records
  -> GET /api/v1/discoveries
  -> Flutter Discover
```

## Repeatability

The underlying scan and discovery stages are idempotent for the same
`(scan_date, universe_version)`. Re-running the command for the same snapshot
must not create duplicate active discovery records.

## Production-model transition

The baseline provider is not a production ML model and must not be represented
as calibrated prediction quality. Replacing it with a trained provider is a
provider implementation change; the operational scan entrypoint and downstream
persistence contract remain unchanged.
