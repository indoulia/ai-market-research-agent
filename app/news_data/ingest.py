"""EPIC-M1.73: provider-agnostic news/corporate-event ingestion.

Mirrors `app.fundamental_data.ingest`'s own provider-boundary pattern
exactly (a `Protocol`, a concrete adapter, an orchestration function that
never imports the concrete adapter), with one deliberate structural
difference: unlike a company's fundamentals (one slowly-changing
snapshot, safe to skip re-fetching for 90 days), news is a continuous
stream -- skipping a fetch because "the last article seen was recent"
would silently miss newer articles published since. So this module
always calls the provider and instead achieves "avoid duplicate
ingestion" (scope) through `NewsEventRecord`'s own
`(stock_id, external_id)` uniqueness: an already-seen article is simply
not re-inserted, never a duplicate row.

Entity resolution (scope: "resolve articles/events to supported
securities") is real, not a heuristic: every ingested item is scoped to
the specific `Stock` whose ticker was queried -- the provider's own API
boundary already resolves it.

Event type and materiality are both derived, once, from the same
deterministic, versioned keyword rule over the article's own headline
text (never sentiment, never fabricated structure the source doesn't
provide) -- this is the one real classification signal available from a
plain headline.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .yahoo import RawNewsItem
from ..models import NewsEventRecord, Stock
from ..refresh_policy import DATA_TYPE_NEWS_EVENT, record_fetch_attempt

NEWS_EVENT_INGESTION_VERSION = "NEI-001"

EVENT_TYPE_CORPORATE_EVENT = "CORPORATE_EVENT"
EVENT_TYPE_NEWS_STORY = "NEWS_STORY"

MATERIALITY_HIGH = "HIGH"
MATERIALITY_LOW = "LOW"

# Fixed, documented, versioned keyword rule: a headline mentioning any of
# these is classified as a likely corporate event with high materiality.
# Deliberately keyword-based, not sentiment/ML -- explainable and honest
# about what it actually detects (scope non-goal: "treating sentiment
# alone as investment evidence").
CORPORATE_EVENT_KEYWORDS = frozenset({
    "earnings", "dividend", "merger", "acquisition", "acquire", "buyback",
    "resign", "resignation", "bankruptcy", "investigation", "fraud",
    "guidance", "ipo", "spin-off", "spinoff", "stake", "lawsuit",
    "settlement", "recall", "downgrade", "upgrade",
})


class NewsEventRecordImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "stock_id",
    "source",
    "external_id",
    "headline",
    "event_type",
    "materiality",
    "published_at",
    "fetched_at",
    "ingestion_rule_version",
    "created_at",
)


@event.listens_for(NewsEventRecord, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise NewsEventRecordImmutableError(
            f"news/event record {target.id} field(s) {changed} cannot be modified after creation"
        )


class NewsEventProvider(Protocol):
    source: str

    def fetch_news(self, symbol: str) -> tuple[RawNewsItem, ...]: ...


def _classify(headline: str) -> tuple[str, str]:
    lowered = headline.lower()
    if any(keyword in lowered for keyword in CORPORATE_EVENT_KEYWORDS):
        return EVENT_TYPE_CORPORATE_EVENT, MATERIALITY_HIGH
    return EVENT_TYPE_NEWS_STORY, MATERIALITY_LOW


def get_latest_news_event(
    session: Session, stock_id: int, *, as_of_timestamp: datetime, event_type: str | None = None
) -> NewsEventRecord | None:
    """The point-in-time-safe read path every consumer (including
    `app.evidence_snapshot`) must use -- a `published_at` in the future
    relative to `as_of_timestamp` is never surfaced (AC: "historical
    analysis cannot see information published after its decision
    time")."""
    query = select(NewsEventRecord).where(
        NewsEventRecord.stock_id == stock_id, NewsEventRecord.published_at <= as_of_timestamp
    )
    if event_type is not None:
        query = query.where(NewsEventRecord.event_type == event_type)
    return session.scalar(query.order_by(NewsEventRecord.published_at.desc()))


def ingest_news_events(
    session: Session,
    provider: NewsEventProvider,
    stock: Stock,
    *,
    requested_at: datetime,
) -> tuple[NewsEventRecord, ...]:
    """Fetches and persists every not-yet-seen news item for `stock`.
    Always calls the provider (see module docstring for why this differs
    from fundamentals' freshness-gated skip); deduplicates purely via
    `NewsEventRecord`'s own `(stock_id, external_id)` uniqueness. Every
    real attempt, successful or failed, is recorded via M1.35's
    `record_fetch_attempt`."""
    try:
        raw_items = provider.fetch_news(stock.symbol)
    except Exception as exc:
        record_fetch_attempt(
            session, data_type=DATA_TYPE_NEWS_EVENT, scope_key=str(stock.id), requested_at=requested_at,
            source_timestamp=None, success=False, failure_reason=str(exc),
        )
        return ()

    existing_external_ids = set(
        session.scalars(
            select(NewsEventRecord.external_id).where(NewsEventRecord.stock_id == stock.id)
        ).all()
    )

    new_records = []
    latest_published_at = None
    for item in raw_items:
        if latest_published_at is None or item.published_at > latest_published_at:
            latest_published_at = item.published_at
        if item.external_id in existing_external_ids:
            continue
        event_type, materiality = _classify(item.headline)
        record = NewsEventRecord(
            stock_id=stock.id,
            source=getattr(provider, "source", "unknown"),
            external_id=item.external_id,
            headline=item.headline,
            event_type=event_type,
            materiality=materiality,
            published_at=item.published_at,
            fetched_at=requested_at,
            ingestion_rule_version=NEWS_EVENT_INGESTION_VERSION,
        )
        session.add(record)
        new_records.append(record)
        existing_external_ids.add(item.external_id)

    record_fetch_attempt(
        session, data_type=DATA_TYPE_NEWS_EVENT, scope_key=str(stock.id), requested_at=requested_at,
        source_timestamp=latest_published_at, success=True,
    )

    session.commit()
    for record in new_records:
        session.refresh(record)
    return tuple(new_records)
