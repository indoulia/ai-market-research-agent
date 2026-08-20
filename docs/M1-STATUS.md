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

- Yahoo Finance daily NSE research-data provider (Upstox remains available for licensed access)
- Corporate-action adjustment policy
- Point-in-time fundamentals
- Event-aware target/stop labeler
- Full walk-forward runner
- Dataset versioning
- Leakage detection
- Production model artifacts
- Live prediction endpoint
- OpenAI Agent

The Yahoo adapter is a research/prototyping source and is not a claim of licensed production
market-data redistribution. It is isolated behind the market-data provider boundary.
