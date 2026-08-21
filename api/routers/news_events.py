"""GET /api/v1/news, GET /api/v1/events and GET /api/v1/events/{eventId}
(EPIC-M1.139, extended by EPIC-M3.5 with eventType/materiality/date
filters and the single-event detail endpoint)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import cursor_paginated, success
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope, SuccessEnvelope
from ..schemas.news_events import EventItem, NewsItem
from ..services.news_events import FeedQuery, get_event, list_events, list_news

router = APIRouter(tags=["news-events"])


@router.get("/news", response_model=CursorEnvelope[NewsItem])
def get_news(
    db: Session = Depends(get_db),
    symbol: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    eventType: str | None = Query(default=None),
    materiality: str | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = list_news(
        db,
        FeedQuery(
            symbol=symbol, sector=sector, industry=industry,
            event_type=eventType, materiality=materiality,
            date_from=from_, date_to=to,
            direction=direction, page_size=pageSize, cursor=cursor,
        ),
    )
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)


@router.get("/events", response_model=CursorEnvelope[EventItem])
def get_events(
    db: Session = Depends(get_db),
    symbol: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    type: str | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = list_events(
        db,
        FeedQuery(
            symbol=symbol, sector=sector, industry=industry,
            event_type=type, date_from=from_, date_to=to,
            direction=direction, page_size=pageSize, cursor=cursor,
        ),
    )
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)


@router.get("/events/{eventId}", response_model=SuccessEnvelope[EventItem])
def get_event_detail(eventId: int, db: Session = Depends(get_db)):
    return success(get_event(db, eventId))
