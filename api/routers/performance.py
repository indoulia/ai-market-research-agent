"""GET /api/v1/performance/* (EPIC-M3.7).

EPIC-M3.7's API Contract names these three paths explicitly
(``/performance/summary``, ``/performance/timeseries``,
``/performance/breakdown``). The underlying metrics were already fully
implemented by EPIC-M1.147 under ``/tracking/*`` (see
``api/services/tracking.py``) -- this router is a thin path alias onto
that same, already-tested service layer so the metrics are computed
exactly once. No logic is duplicated here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import success
from ..schemas.common import SuccessEnvelope
from ..schemas.tracking import BreakdownResponse, TimeseriesResponse, TrackingSummary
from ..services.tracking import get_breakdown, get_summary, get_timeseries

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/summary", response_model=SuccessEnvelope[TrackingSummary])
def get_performance_summary(range: str = Query(default="30d"), db: Session = Depends(get_db)):
    return success(get_summary(db, range))


@router.get("/timeseries", response_model=SuccessEnvelope[TimeseriesResponse])
def get_performance_timeseries(
    metric: str = Query(..., description="trust|hitRate|return|calibration"),
    range: str = Query(default="30d"),
    bucket: str = Query(default="day", description="day|week"),
    db: Session = Depends(get_db),
):
    return success(get_timeseries(db, metric, range, bucket))


@router.get("/breakdown", response_model=SuccessEnvelope[BreakdownResponse])
def get_performance_breakdown(
    dimension: str = Query(..., description="horizon|sector|marketCap|regime|setup|stock"), db: Session = Depends(get_db)
):
    return success(get_breakdown(db, dimension))
