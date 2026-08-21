from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DataFetchAttempt, NewsEventRecord, Stock
from app.news_data.ingest import (
    EVENT_TYPE_CORPORATE_EVENT,
    EVENT_TYPE_NEWS_STORY,
    MATERIALITY_HIGH,
    MATERIALITY_LOW,
    NEWS_EVENT_INGESTION_VERSION,
    NewsEventRecordImmutableError,
    get_latest_news_event,
    ingest_news_events,
)
from app.news_data.yahoo import RawNewsItem
from app.refresh_policy import DATA_TYPE_NEWS_EVENT

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _make_stock(session, symbol="RELIANCE"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.commit()
    session.refresh(stock)
    return stock


class _FakeProvider:
    source = "fake-provider"

    def __init__(self, items=(), error=None):
        self.items = items
        self.error = error
        self.calls = 0

    def fetch_news(self, symbol):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.items


def test_ingestion_classifies_corporate_event_by_keyword(session):
    stock = _make_stock(session)
    provider = _FakeProvider(items=[RawNewsItem("a1", "Company announces record earnings beat", T0)])

    records = ingest_news_events(session, provider, stock, requested_at=T0)

    assert len(records) == 1
    assert records[0].event_type == EVENT_TYPE_CORPORATE_EVENT
    assert records[0].materiality == MATERIALITY_HIGH
    assert records[0].ingestion_rule_version == NEWS_EVENT_INGESTION_VERSION


def test_ingestion_classifies_generic_story_as_news(session):
    stock = _make_stock(session)
    provider = _FakeProvider(items=[RawNewsItem("a2", "Analysts discuss sector outlook for the week", T0)])

    records = ingest_news_events(session, provider, stock, requested_at=T0)

    assert records[0].event_type == EVENT_TYPE_NEWS_STORY
    assert records[0].materiality == MATERIALITY_LOW


def test_repeat_fetch_does_not_duplicate_already_seen_articles(session):
    stock = _make_stock(session)
    provider = _FakeProvider(items=[RawNewsItem("dup-1", "Quarterly results announced", T0)])

    first = ingest_news_events(session, provider, stock, requested_at=T0)
    second = ingest_news_events(session, provider, stock, requested_at=T0 + timedelta(hours=1))

    assert len(first) == 1
    assert len(second) == 0  # same article, already ingested -- not a duplicate row
    assert session.query(NewsEventRecord).count() == 1


def test_new_article_alongside_a_seen_one_is_ingested(session):
    stock = _make_stock(session)
    provider = _FakeProvider(items=[RawNewsItem("dup-1", "First story", T0)])
    ingest_news_events(session, provider, stock, requested_at=T0)

    provider.items = [
        RawNewsItem("dup-1", "First story", T0),
        RawNewsItem("new-1", "Second, newer story", T0 + timedelta(hours=2)),
    ]
    second = ingest_news_events(session, provider, stock, requested_at=T0 + timedelta(hours=3))

    assert [r.external_id for r in second] == ["new-1"]
    assert session.query(NewsEventRecord).count() == 2


def test_provider_error_records_failed_attempt_and_no_rows(session):
    stock = _make_stock(session)
    provider = _FakeProvider(error=RuntimeError("timeout"))

    records = ingest_news_events(session, provider, stock, requested_at=T0)

    assert records == ()
    assert session.query(NewsEventRecord).count() == 0
    attempt = session.query(DataFetchAttempt).filter_by(data_type=DATA_TYPE_NEWS_EVENT).one()
    assert attempt.success is False
    assert "timeout" in attempt.failure_reason


def test_point_in_time_safety_hides_future_articles(session):
    stock = _make_stock(session)
    provider = _FakeProvider(items=[
        RawNewsItem("early", "Old story", T0),
        RawNewsItem("late", "Future-dated story", T0 + timedelta(days=30)),
    ])
    ingest_news_events(session, provider, stock, requested_at=T0)

    as_of_before = get_latest_news_event(session, stock.id, as_of_timestamp=T0 + timedelta(days=1))
    as_of_after = get_latest_news_event(session, stock.id, as_of_timestamp=T0 + timedelta(days=31))

    assert as_of_before.external_id == "early"
    assert as_of_after.external_id == "late"


def test_get_latest_news_event_filters_by_event_type(session):
    stock = _make_stock(session)
    provider = _FakeProvider(items=[
        RawNewsItem("story-1", "Generic market commentary", T0),
        RawNewsItem("event-1", "Company announces merger agreement", T0 + timedelta(hours=1)),
    ])
    ingest_news_events(session, provider, stock, requested_at=T0 + timedelta(hours=2))

    latest_any = get_latest_news_event(session, stock.id, as_of_timestamp=T0 + timedelta(days=1))
    latest_event = get_latest_news_event(
        session, stock.id, as_of_timestamp=T0 + timedelta(days=1), event_type=EVENT_TYPE_CORPORATE_EVENT
    )

    assert latest_any.external_id == "event-1"
    assert latest_event.external_id == "event-1"


def test_news_event_record_is_immutable(session):
    stock = _make_stock(session)
    provider = _FakeProvider(items=[RawNewsItem("a1", "Some story", T0)])
    records = ingest_news_events(session, provider, stock, requested_at=T0)

    records[0].headline = "edited after the fact"
    with pytest.raises(NewsEventRecordImmutableError):
        session.commit()
    session.rollback()
