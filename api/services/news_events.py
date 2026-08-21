"""Query service backing GET /api/v1/news, GET /api/v1/events and
GET /api/v1/events/{eventId} (EPIC-M1.139, extended by EPIC-M3.5).

`/news` projects M1.90's `NewsEventRecord`; `/events` projects M1.90's
`CorporateAction`. Both support symbol/sector/industry filtering and real
keyset (cursor) pagination on `(publishedAt|effectiveAt, id)`, matching
M1.135/M1.139's discoveries pattern -- both tables grow without bound.

EPIC-M3.5 added `eventType`/date-range filtering to both feeds (`type` on
`/events` reuses the field the item already returns as `type`) and a
`materiality` filter on `/news`, where it's a real, populated column.
`CorporateAction` has no `materiality` column at all (`/events` items
always report `materiality: null`, unchanged since M1.139) so `/events`
deliberately does not accept a `materiality` query param -- accepting one
that could never match anything would be a silent lie about what the data
supports, not a real filter.

Honest, named gap (AC: "duplicate/syndicated events are represented once
at the API layer"): same-source duplicates are prevented at ingestion by
`NewsEventRecord`'s `(stock_id, external_id)` uniqueness constraint, but
no cross-source content-based dedup (the same real-world event reported
by two different providers) is implemented -- that would need fuzzy
content matching, out of scope for an API-layer query service.

`affectedSecurities` is always a single-element list (the one stock a
`NewsEventRecord` is linked to) -- this platform doesn't model
multi-security news yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CorporateAction, NewsEventRecord, Stock

from ..errors import NotFoundError, ValidationError
from ..pagination import DEFAULT_PAGE_SIZE
from ..schemas.news_events import EventItem, NewsItem
from .keyset import decode_cursor, encode_cursor, keyset_predicate

DIRECTIONS = ("asc", "desc")


@dataclass
class FeedQuery:
    symbol: str | None = None
    sector: str | None = None
    industry: str | None = None
    event_type: str | None = None
    materiality: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    direction: str = "desc"
    page_size: int = DEFAULT_PAGE_SIZE
    cursor: str | None = None


@dataclass
class NewsPage:
    items: list[NewsItem]
    next_cursor: str | None


@dataclass
class EventsPage:
    items: list[EventItem]
    next_cursor: str | None


def _validate_direction(direction: str) -> None:
    if direction not in DIRECTIONS:
        raise ValidationError(f"Unknown direction '{direction}'.", field_errors={"direction": f"must be one of {DIRECTIONS}"})


def list_news(session: Session, query: FeedQuery) -> NewsPage:
    _validate_direction(query.direction)
    stmt = (
        select(NewsEventRecord, Stock.symbol)
        .join(Stock, Stock.id == NewsEventRecord.stock_id)
    )
    if query.symbol is not None:
        stmt = stmt.where(Stock.symbol == query.symbol)
    if query.sector is not None:
        stmt = stmt.where(Stock.sector == query.sector)
    if query.industry is not None:
        stmt = stmt.where(Stock.industry == query.industry)
    if query.event_type is not None:
        stmt = stmt.where(NewsEventRecord.event_type == query.event_type)
    if query.materiality is not None:
        stmt = stmt.where(NewsEventRecord.materiality == query.materiality)
    if query.date_from is not None:
        stmt = stmt.where(NewsEventRecord.published_at >= query.date_from)
    if query.date_to is not None:
        stmt = stmt.where(NewsEventRecord.published_at <= query.date_to)

    descending = query.direction == "desc"
    sort_expr = NewsEventRecord.published_at
    id_col = NewsEventRecord.id
    if query.cursor:
        cursor_value, cursor_id = decode_cursor(query.cursor, is_datetime=True)
        if cursor_value is not None:
            stmt = stmt.where(keyset_predicate(sort_expr, id_col, cursor_value, cursor_id, descending=descending))

    order_expr = sort_expr.desc() if descending else sort_expr.asc()
    id_order = id_col.desc() if descending else id_col.asc()
    stmt = stmt.order_by(order_expr, id_order).limit(query.page_size + 1)

    rows = session.execute(stmt).all()
    has_more = len(rows) > query.page_size
    rows = rows[: query.page_size]

    items = [
        NewsItem(
            symbol=symbol,
            headline=record.headline,
            source=record.source,
            publishedAt=record.published_at,
            detectedAt=record.fetched_at,
            materiality=record.materiality,
            eventType=record.event_type,
            affectedSecurities=[symbol],
            evidenceId=record.id,
        )
        for record, symbol in rows
    ]

    next_cursor = None
    if has_more and rows:
        last_record, _symbol = rows[-1]
        next_cursor = encode_cursor(last_record.published_at, last_record.id)

    return NewsPage(items=items, next_cursor=next_cursor)


def list_events(session: Session, query: FeedQuery) -> EventsPage:
    _validate_direction(query.direction)
    stmt = (
        select(CorporateAction, Stock.symbol)
        .join(Stock, Stock.id == CorporateAction.stock_id)
    )
    if query.symbol is not None:
        stmt = stmt.where(Stock.symbol == query.symbol)
    if query.sector is not None:
        stmt = stmt.where(Stock.sector == query.sector)
    if query.industry is not None:
        stmt = stmt.where(Stock.industry == query.industry)
    if query.event_type is not None:
        stmt = stmt.where(CorporateAction.action_type == query.event_type)
    if query.date_from is not None:
        stmt = stmt.where(CorporateAction.effective_date >= query.date_from.date())
    if query.date_to is not None:
        stmt = stmt.where(CorporateAction.effective_date <= query.date_to.date())

    descending = query.direction == "desc"
    sort_expr = CorporateAction.recorded_at
    id_col = CorporateAction.id
    if query.cursor:
        cursor_value, cursor_id = decode_cursor(query.cursor, is_datetime=True)
        if cursor_value is not None:
            stmt = stmt.where(keyset_predicate(sort_expr, id_col, cursor_value, cursor_id, descending=descending))

    order_expr = sort_expr.desc() if descending else sort_expr.asc()
    id_order = id_col.desc() if descending else id_col.asc()
    stmt = stmt.order_by(order_expr, id_order).limit(query.page_size + 1)

    rows = session.execute(stmt).all()
    has_more = len(rows) > query.page_size
    rows = rows[: query.page_size]

    items = [_to_event_item(record, symbol) for record, symbol in rows]

    next_cursor = None
    if has_more and rows:
        last_record, _symbol = rows[-1]
        next_cursor = encode_cursor(last_record.recorded_at, last_record.id)

    return EventsPage(items=items, next_cursor=next_cursor)


def _to_event_item(record: CorporateAction, symbol: str) -> EventItem:
    return EventItem(
        symbol=symbol,
        type=record.action_type,
        title=f"{record.action_type} ({symbol})",
        effectiveAt=datetime.combine(record.effective_date, datetime.min.time(), tzinfo=timezone.utc),
        detectedAt=record.recorded_at,
        materiality=None,
        source=record.source,
        evidenceId=record.id,
    )


def get_event(session: Session, event_id: int) -> EventItem:
    """`GET /api/v1/events/{eventId}` (EPIC-M3.5) -- single corporate-action
    projection, same mapping `list_events` uses, keyed on `CorporateAction.id`
    (== the `evidenceId` every `/events` list item already returns)."""
    row = session.execute(
        select(CorporateAction, Stock.symbol)
        .join(Stock, Stock.id == CorporateAction.stock_id)
        .where(CorporateAction.id == event_id)
    ).first()
    if row is None:
        raise NotFoundError("event", str(event_id))
    record, symbol = row
    return _to_event_item(record, symbol)
