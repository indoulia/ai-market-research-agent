from fastapi import FastAPI
from sqlalchemy import text
from .db import SessionLocal
from api.app import register_api

app = FastAPI(title="Market Agent M1", version="0.1.0")
register_api(app)

@app.get("/health")
def health():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "component": "market-agent-m1"}

@app.get("/api/models")
def models():
    with SessionLocal() as db:
        rows = db.execute(text(
            "SELECT version, model_name, feature_version, status, metrics_json, created_at "
            "FROM model_versions ORDER BY created_at DESC"
        )).mappings().all()
    return {"models": [dict(r) for r in rows]}
