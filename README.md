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
