# AI Market Research Agent

M1 foundation for an AI-assisted market research and short-horizon prediction system.

## M1 status

- FastAPI service
- PostgreSQL persistence
- Alembic migrations
- Prediction/outcome/model-version schema
- Environment-based configuration
- Designed for point-in-time datasets and walk-forward validation

## Local setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# edit .env
alembic upgrade head
uvicorn app.main:app --reload
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

## Important

The system is a research/backtesting platform, not a guarantee of investment returns. The target confidence score must be calibrated and validated out-of-sample before it is used for decision support.
