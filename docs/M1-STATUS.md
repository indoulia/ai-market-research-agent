# M1 Status

## Frozen scope

Historical Prediction Engine only.

## Implemented scaffold

- PostgreSQL schema
- SQLAlchemy models
- Alembic migration
- Technical feature baseline
- Forward-label baseline
- XGBoost prediction baseline
- Isotonic probability calibration
- Walk-forward window primitive
- FastAPI health/model endpoints
- Test scaffold

## Not yet production-ready

- Real NSE historical data provider
- Corporate-action adjustment policy
- Point-in-time fundamentals
- Event-aware target/stop labeler
- Full walk-forward runner
- Dataset versioning
- Leakage detection
- Production model artifacts
- Live prediction endpoint
- OpenAI Agent

## Next implementation task

M1.1 — finalize the real historical NSE data contract and ingestion adapter.
