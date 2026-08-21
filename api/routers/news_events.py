"""GET /api/v1/news and GET /api/v1/events (EPIC-M1.139)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import cursor_paginated
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope
from ..schemas.news_events import EventItem, NewsItem
from ..services.news_events import FeedQuery, list_events, list_news

router = APIRouter(tags=["news-events"])


@router.get("/news", response_model=CursorEnvelope[NewsItem])
def get_news(
    db: Session = Depends(get_db),
    symbol: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = list_news(db, FeedQuery(symbol=symbol, sector=sector, industry=industry, direction=direction, page_size=pageSize, cursor=cursor))
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)


@router.get("/events", response_model=CursorEnvelope[EventItem])
def get_events(
    db: Session = Depends(get_db),
    symbol: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = list_events(db, FeedQuery(symbol=symbol, sector=sector, industry=industry, direction=direction, page_size=pageSize, cursor=cursor))
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)
