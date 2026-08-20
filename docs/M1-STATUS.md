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
- Deterministic historical OHLCV quality rules and persisted validation reports
- Yahoo Finance daily NSE research-data provider
- Immutable positive-recommendation history persistence and query support (M1.4)

## Not yet production-ready

- Validated production-scale NSE historical dataset
- Corporate-action adjustment policy
- Point-in-time fundamentals
- Event-aware target/stop labeler
- Full walk-forward runner
- Dataset versioning
- Leakage detection
- Recommendation outcome evaluation
- Production model artifacts
- Live prediction endpoint
- OpenAI Agent

The Yahoo adapter is a research/prototyping source and is not a claim of licensed production
market-data redistribution. It is isolated behind the market-data provider boundary.

## Next implementation tasks

- M1.5 — evaluate recommendation outcomes at their predefined horizon (depends on M1.4).
