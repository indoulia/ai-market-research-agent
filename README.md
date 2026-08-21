# Market Agent — M1 Historical Prediction Engine

Frozen scope:
- Historical NSE-oriented dataset
- Point-in-time feature generation
- 1/3/5/7 trading-day targets
- Baseline ML prediction
- Probability calibration
- Walk-forward backtesting foundation
- PostgreSQL persistence
- Prediction API

Out of scope for M1:
- OpenAI research agent orchestration
- Automated trading
- Broker integration
- Autonomous model promotion
- News/LLM prediction
- Reinforcement learning

## PostgreSQL

This project intentionally does NOT create another PostgreSQL server. It expects your existing Docker PostgreSQL instance.

Create the application database once:

```sql
CREATE DATABASE market_agent;
```

Configure `.env` from `.env.example`. If your Docker PostgreSQL exposes port 5432:

```text
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/market_agent
```

## Run

Python 3.11+ recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/health`

## Historical dataset quality gate

After applying migrations and ingesting candles, validate a date range with:

```powershell
python -m scripts.validate_market_data --from-date 2026-01-01 --to-date 2026-06-30
```

Add one or more `--stock-id` options to scope the run. The command checks positive
OHLCV values, valid high/low relationships, duplicate timestamps, NSE-midnight
timestamps, unexpected sessions, and missing sessions. It writes the complete JSON
result to `dataset_validation_runs`; `PASSED` and exit code `0` are the downstream
modeling/backtest gate. `FAILED` returns exit code `1`.

By default, weekdays are expected sessions. Code that has an official NSE holiday
calendar should call `validate_market_prices(..., expected_sessions=...)` so holidays
are excluded explicitly and audibly.

The current implementation is a working M1 scaffold. It does not claim to produce live investment predictions until the real historical NSE data adapter is connected and validated.

## Docker Compose (local end-to-end: ingestion → scan → API → UI)

```powershell
Copy-Item .env.example .env   # set MARKET_DATA_PROVIDER, tokens/symbols as needed
docker compose up -d postgres
docker compose run --rm migrate
docker compose up -d api web
```

`api` (port 8000) and `web` (port 8080) start every time; `ingest` and `discovery` are
on-demand (`profiles: ["tools"]`) and never run as part of `docker compose up`:

```powershell
# 1. Load NSE universe + daily candles from whichever provider MARKET_DATA_PROVIDER selects
docker compose run --rm ingest --from-date 2026-06-01 --to-date 2026-08-21

# 2. Turn that market data into real scan_candidates + discovery_records
docker compose run --rm discovery --scan-date 2026-08-20
```

`discovery` resolves its `SignalProvider` from `DISCOVERY_SIGNAL_PROVIDER` (`baseline`
today — a deterministic technical-signal heuristic, not a trained model; see
`app/baseline_signal.py`) and prints a machine-readable run summary (stocks scanned,
candidates eligible/excluded and why, discoveries/generations/selections created). It
is safe to re-run for the same `--scan-date`: already-persisted rows are returned
unchanged rather than duplicated. An empty/insufficient market-price table produces an
explicit `"status": "no_market_data"` summary, not an exception or fabricated data; an
unresolvable `DISCOVERY_SIGNAL_PROVIDER` exits non-zero with an actionable message
instead of running.

Once `discovery` has run, `GET /api/v1/discoveries` (and the Flutter Discover screen
served from `web`) reflect the persisted records directly — no separate backend step.
