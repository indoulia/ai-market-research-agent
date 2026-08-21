"""GET /api/v1/recommendations/{recommendationId}[/history|/events|/outcome] (EPIC-M1.137)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import cursor_paginated, success
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope, SuccessEnvelope
from ..schemas.recommendation_detail import EventItem, HistoryItem, OutcomeResponse, RecommendationDetail
from ..services.recommendation_detail import get_detail, get_events, get_history, get_outcome

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/{recommendationId}", response_model=SuccessEnvelope[RecommendationDetail])
def get_recommendation_detail(recommendationId: int, db: Session = Depends(get_db)):
    return success(get_detail(db, recommendationId))


@router.get("/{recommendationId}/history", response_model=CursorEnvelope[HistoryItem])
def get_recommendation_history(
    recommendationId: int,
    db: Session = Depends(get_db),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = get_history(db, recommendationId, from_ts=from_, to_ts=to, cursor=cursor, page_size=pageSize)
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)


@router.get("/{recommendationId}/events", response_model=CursorEnvelope[EventItem])
def get_recommendation_events(
    recommendationId: int,
    db: Session = Depends(get_db),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = get_events(db, recommendationId, cursor=cursor, page_size=pageSize)
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)


@router.get("/{recommendationId}/outcome", response_model=SuccessEnvelope[OutcomeResponse])
def get_recommendation_outcome(recommendationId: int, db: Session = Depends(get_db)):
    return success(get_outcome(db, recommendationId))
