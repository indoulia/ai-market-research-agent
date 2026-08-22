"""GET /api/v1/tracking/* (EPIC-M1.147; filters added by EPIC-M3.15)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import cursor_paginated, success
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope, SuccessEnvelope
from ..schemas.tracking import BreakdownResponse, TimeseriesResponse, TrackedPrediction, TrackingSummary
from ..services.tracking import get_breakdown, get_summary, get_timeseries, list_tracked_predictions, make_filters

router = APIRouter(prefix="/tracking", tags=["tracking"])

# EPIC-M3.15: the filter query surface shared by every endpoint below.
_FILTER_QUERY_DOC = "narrows the result to genuine predictions matching this dimension"


def _filters_dep(
    horizon: int | None = Query(default=None, description=f"horizon in days (1-7) -- {_FILTER_QUERY_DOC}"),
    sector: str | None = Query(default=None, description=_FILTER_QUERY_DOC),
    marketCap: str | None = Query(default=None, description=_FILTER_QUERY_DOC),
    regime: str | None = Query(default=None, description=_FILTER_QUERY_DOC),
    symbol: str | None = Query(default=None, description=_FILTER_QUERY_DOC),
    setup: str | None = Query(default=None, description=_FILTER_QUERY_DOC),
):
    return make_filters(horizon=horizon, sector=sector, market_cap=marketCap, regime=regime, symbol=symbol, setup=setup)


@router.get("/summary", response_model=SuccessEnvelope[TrackingSummary])
def get_tracking_summary(
    range: str = Query(default="30d"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    filters=Depends(_filters_dep),
    db: Session = Depends(get_db),
):
    return success(get_summary(db, range, from_=from_, to_=to, filters=filters))


@router.get("/timeseries", response_model=SuccessEnvelope[TimeseriesResponse])
def get_tracking_timeseries(
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
def get_tracking_breakdown(
    dimension: str = Query(..., description="horizon|sector|marketCap|regime|setup|stock"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    filters=Depends(_filters_dep),
    db: Session = Depends(get_db),
):
    return success(get_breakdown(db, dimension, from_=from_, to_=to, filters=filters))


@router.get("/predictions", response_model=CursorEnvelope[TrackedPrediction])
def get_tracking_predictions(
    status: str = Query(..., description="active|closed"),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    filters=Depends(_filters_dep),
    db: Session = Depends(get_db),
):
    page = list_tracked_predictions(db, status, cursor=cursor, page_size=pageSize, from_=from_, to_=to, filters=filters)
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)
