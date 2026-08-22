"""GET /api/v1/performance/* (EPIC-M3.7; filters added by EPIC-M3.15).

EPIC-M3.7's API Contract names these three paths explicitly
(``/performance/summary``, ``/performance/timeseries``,
``/performance/breakdown``). The underlying metrics were already fully
implemented by EPIC-M1.147 under ``/tracking/*`` (see
``api/services/tracking.py``) -- this router is a thin path alias onto
that same, already-tested service layer so the metrics are computed
exactly once. No logic is duplicated here.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import success
from ..schemas.common import SuccessEnvelope
from ..schemas.tracking import BreakdownResponse, TimeseriesResponse, TrackingSummary
from ..services.tracking import get_breakdown, get_summary, get_timeseries, make_filters

router = APIRouter(prefix="/performance", tags=["performance"])


def _filters_dep(
    horizon: int | None = Query(default=None),
    sector: str | None = Query(default=None),
    marketCap: str | None = Query(default=None),
    regime: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    setup: str | None = Query(default=None),
):
    return make_filters(horizon=horizon, sector=sector, market_cap=marketCap, regime=regime, symbol=symbol, setup=setup)


@router.get("/summary", response_model=SuccessEnvelope[TrackingSummary])
def get_performance_summary(
    range: str = Query(default="30d"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    filters=Depends(_filters_dep),
    db: Session = Depends(get_db),
):
    return success(get_summary(db, range, from_=from_, to_=to, filters=filters))


@router.get("/timeseries", response_model=SuccessEnvelope[TimeseriesResponse])
def get_performance_timeseries(
    metric: str = Query(..., description="trust|hitRate|return|calibration"),
    range: str = Query(default="30d"),
    bucket: str = Query(default="day", description="day|week"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    filters=Depends(_filters_dep),
    db: Session = Depends(get_db),
):
    return success(get_timeseries(db, metric, range, bucket, from_=from_, to_=to, filters=filters))


@router.get("/breakdown", response_model=SuccessEnvelope[BreakdownResponse])
def get_performance_breakdown(
    dimension: str = Query(..., description="horizon|sector|marketCap|regime|setup|stock"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    filters=Depends(_filters_dep),
    db: Session = Depends(get_db),
):
    return success(get_breakdown(db, dimension, from_=from_, to_=to, filters=filters))
