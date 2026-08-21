"""GET /api/v1/predictions/active[/{predictionId}] (EPIC-M3.8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import cursor_paginated, success
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope, SuccessEnvelope
from ..schemas.predictions_active import ActivePrediction
from ..services.predictions_active import get_active_prediction, list_active_predictions

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/active", response_model=CursorEnvelope[ActivePrediction])
def get_active_predictions(
    db: Session = Depends(get_db),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = list_active_predictions(db, cursor=cursor, page_size=pageSize)
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)


@router.get("/active/{predictionId}", response_model=SuccessEnvelope[ActivePrediction])
def get_active_prediction_detail(predictionId: int, db: Session = Depends(get_db)):
    return success(get_active_prediction(db, predictionId))
