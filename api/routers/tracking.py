"""GET /api/v1/tracking/* (EPIC-M1.147)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import cursor_paginated, success
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope, SuccessEnvelope
from ..schemas.tracking import BreakdownResponse, TimeseriesResponse, TrackedPrediction, TrackingSummary
from ..services.tracking import get_breakdown, get_summary, get_timeseries, list_tracked_predictions

router = APIRouter(prefix="/tracking", tags=["tracking"])


@router.get("/summary", response_model=SuccessEnvelope[TrackingSummary])
def get_tracking_summary(range: str = Query(default="30d"), db: Session = Depends(get_db)):
    return success(get_summary(db, range))


@router.get("/timeseries", response_model=SuccessEnvelope[TimeseriesResponse])
def get_tracking_timeseries(
    metric: str = Query(..., description="trust|hitRate|return|calibration"),
    range: str = Query(default="30d"),
    bucket: str = Query(default="day", description="day|week"),
    db: Session = Depends(get_db),
):
    return success(get_timeseries(db, metric, range, bucket))


@router.get("/breakdown", response_model=SuccessEnvelope[BreakdownResponse])
def get_tracking_breakdown(
    dimension: str = Query(..., description="horizon|sector|marketCap|regime|setup|stock"), db: Session = Depends(get_db)
):
    return success(get_breakdown(db, dimension))


@router.get("/predictions", response_model=CursorEnvelope[TrackedPrediction])
def get_tracking_predictions(
    status: str = Query(..., description="active|closed"),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    page = list_tracked_predictions(db, status, cursor=cursor, page_size=pageSize)
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)
