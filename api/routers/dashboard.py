"""GET /api/v1/dashboard/snapshot (EPIC-M3.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import success
from ..schemas.common import SuccessEnvelope
from ..schemas.dashboard import DashboardSnapshot
from ..services.dashboard import DASHBOARD_DEFAULT_LIMIT, DASHBOARD_MAX_LIMIT, DashboardQuery, get_dashboard_snapshot

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/snapshot", response_model=SuccessEnvelope[DashboardSnapshot])
def get_snapshot(
    db: Session = Depends(get_db),
    market: str | None = Query(default=None, description="Exchange, e.g. nse"),
    horizon: int | None = Query(default=None, description="1|3|5|7 trading-day horizon"),
    limit: int = Query(default=DASHBOARD_DEFAULT_LIMIT, ge=1, le=DASHBOARD_MAX_LIMIT),
    sector: str | None = Query(default=None, description="Additive quick filter, reuses M1.135's `sector` vocabulary"),
    marketCapBucket: str | None = Query(default=None, description="LARGE_CAP|MID_CAP|SMALL_CAP|UNCLASSIFIED"),
):
    snapshot = get_dashboard_snapshot(
        db,
        DashboardQuery(market=market, horizon=horizon, limit=limit, sector=sector, market_cap_bucket=marketCapBucket),
    )
    return success(snapshot)
