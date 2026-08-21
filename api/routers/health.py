"""GET /api/v1/health (EPIC-M1.132)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import success
from ..errors import InternalError
from ..schemas.common import SuccessEnvelope
from ..schemas.health import HealthResponse
from ..versioning import API_VERSION

router = APIRouter(tags=["health"])


@router.get("/health", response_model=SuccessEnvelope[HealthResponse])
def get_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on infra availability
        raise InternalError("Database connectivity check failed.") from exc
    return success(HealthResponse(status="ok", component="market-agent-m1", apiVersion=API_VERSION))
