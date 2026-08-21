from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import FundamentalDataRecord, NewsEventRecord, Stock
from app.source_authority_resolution import (
    FACT_TYPE_FUNDAMENTAL_EPS,
    FACT_TYPE_NEWS_EVENT,
    REASON_AUTHORITATIVE_SOURCE_OVERRIDE,
    REASON_INSUFFICIENT_SOURCES,
    REASON_NO_CONFLICT,
    REASON_SINGLE_SOURCE,
    REASON_TIMESTAMP_PRECEDENCE_TIEBREAK,
    RESOLUTION_VERSION,
    get_resolved_fact_history,
    resolve_fundamental_fact,
    resolve_news_event_fact,
)

AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
PERIOD_END = date(2026, 12, 31)
_counter = iter(range(1000000))


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


@pytest.fixture
def stock(session):
    s = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(s)
    session.commit()
    return s


def _add_fundamental(session, stock, *, source, eps, fetched_at=AS_OF, period_end_date=PERIOD_END):
    session.add(FundamentalDataRecord(
        stock_id=stock.id, source=source, period_end_date=period_end_date, eps=eps,
        published_at=fetched_at, fetched_at=fetched_at, ingestion_rule_version="FDI-001",
    ))
    session.commit()


def _add_news(session, stock, *, source, headline, event_type="EARNINGS", published_at=AS_OF):
    n = next(_counter)
    session.add(NewsEventRecord(
        stock_id=stock.id, source=source, external_id=f"ext-{n}",
        headline=headline, event_type=event_type, materiality="MEDIUM", published_at=published_at,
        fetched_at=published_at, ingestion_rule_version="NEI-001",
    ))
    session.commit()


def test_fundamental_insufficient_sources_with_no_data(session, stock):
    resolved = resolve_fundamental_fact(session, stock_id=stock.id, period_end_date=PERIOD_END, resolved_at=AS_OF)

    assert resolved.resolution_reason == REASON_INSUFFICIENT_SOURCES
    assert resolved.resolved_value_numeric is None
    assert resolved.resolution_rule_version == RESOLUTION_VERSION


def test_fundamental_single_source(session, stock):
    _add_fundamental(session, stock, source="yahoo-finance", eps=Decimal("5.00"))

    resolved = resolve_fundamental_fact(session, stock_id=stock.id, period_end_date=PERIOD_END, resolved_at=AS_OF)

    assert resolved.resolution_reason == REASON_SINGLE_SOURCE
    assert resolved.resolved_value_numeric == Decimal("5.00")
    assert resolved.winning_source == "yahoo-finance"


def test_fundamental_no_conflict_when_sources_agree(session, stock):
    _add_fundamental(session, stock, source="yahoo-finance", eps=Decimal("5.00"))
    _add_fundamental(session, stock, source="alpha-vantage", eps=Decimal("5.02"))

    resolved = resolve_fundamental_fact(session, stock_id=stock.id, period_end_date=PERIOD_END, resolved_at=AS_OF)

    assert resolved.resolution_reason == REASON_NO_CONFLICT
    assert resolved.conflicting is False
    assert resolved.source_count == 2


def test_fundamental_timestamp_precedence_tiebreak_when_all_tiers_equal_and_conflicting(session, stock):
    _add_fundamental(session, stock, source="yahoo-finance", eps=Decimal("5.00"), fetched_at=AS_OF)
    _add_fundamental(session, stock, source="alpha-vantage", eps=Decimal("8.00"), fetched_at=AS_OF + timedelta(hours=1))

    resolved = resolve_fundamental_fact(session, stock_id=stock.id, period_end_date=PERIOD_END, resolved_at=AS_OF)

    assert resolved.resolution_reason == REASON_TIMESTAMP_PRECEDENCE_TIEBREAK
    assert resolved.conflicting is True
    assert resolved.winning_source == "alpha-vantage"  # most recently fetched wins the tiebreak
    assert resolved.resolved_value_numeric == Decimal("8.00")


def test_fundamental_authoritative_source_overrides_majority(session, stock, monkeypatch):
    import app.source_authority_resolution as sar
    monkeypatch.setitem(
        sar.AUTHORITY_TIER_BY_FACT_TYPE, FACT_TYPE_FUNDAMENTAL_EPS,
        {"yahoo-finance": Decimal("1"), "alpha-vantage": Decimal("1"), "finnhub": Decimal("2")},
    )
    _add_fundamental(session, stock, source="yahoo-finance", eps=Decimal("5.00"))
    _add_fundamental(session, stock, source="alpha-vantage", eps=Decimal("5.05"))
    _add_fundamental(session, stock, source="finnhub", eps=Decimal("9.00"))

    resolved = resolve_fundamental_fact(session, stock_id=stock.id, period_end_date=PERIOD_END, resolved_at=AS_OF)

    assert resolved.resolution_reason == REASON_AUTHORITATIVE_SOURCE_OVERRIDE
    assert resolved.winning_source == "finnhub"
    assert resolved.resolved_value_numeric == Decimal("9.00")  # outnumbered 2-to-1 but wins on authority


def test_fundamental_idempotent(session, stock):
    _add_fundamental(session, stock, source="yahoo-finance", eps=Decimal("5.00"))

    first = resolve_fundamental_fact(session, stock_id=stock.id, period_end_date=PERIOD_END, resolved_at=AS_OF)
    second = resolve_fundamental_fact(session, stock_id=stock.id, period_end_date=PERIOD_END, resolved_at=AS_OF)

    assert first.id == second.id
    assert len(get_resolved_fact_history(session, fact_type=FACT_TYPE_FUNDAMENTAL_EPS, stock_id=stock.id, fact_key=PERIOD_END.isoformat())) == 1


def test_news_insufficient_sources_when_no_records(session, stock):
    resolved = resolve_news_event_fact(session, stock_id=stock.id, event_type="EARNINGS", anchor_published_at=AS_OF, resolved_at=AS_OF)

    assert resolved.resolution_reason == REASON_INSUFFICIENT_SOURCES


def test_news_single_source(session, stock):
    _add_news(session, stock, source="yahoo-finance", headline="Q3 earnings beat estimates")

    resolved = resolve_news_event_fact(session, stock_id=stock.id, event_type="EARNINGS", anchor_published_at=AS_OF, resolved_at=AS_OF)

    assert resolved.resolution_reason == REASON_SINGLE_SOURCE
    assert resolved.resolved_value_text == "Q3 earnings beat estimates"


def test_news_syndicated_duplicate_headline_is_not_a_conflict(session, stock):
    _add_news(session, stock, source="yahoo-finance", headline="Q3 earnings beat estimates", published_at=AS_OF)
    _add_news(session, stock, source="finnhub", headline="Q3 EARNINGS BEAT ESTIMATES", published_at=AS_OF + timedelta(minutes=5))

    resolved = resolve_news_event_fact(session, stock_id=stock.id, event_type="EARNINGS", anchor_published_at=AS_OF, resolved_at=AS_OF)

    assert resolved.resolution_reason == REASON_NO_CONFLICT
    assert resolved.conflicting is False
    assert resolved.source_count == 2


def test_news_timestamp_precedence_tiebreak_when_headlines_genuinely_differ(session, stock):
    _add_news(session, stock, source="yahoo-finance", headline="Q3 earnings beat estimates", published_at=AS_OF)
    _add_news(session, stock, source="finnhub", headline="Company raises full-year guidance after strong Q3", published_at=AS_OF + timedelta(hours=1))

    resolved = resolve_news_event_fact(session, stock_id=stock.id, event_type="EARNINGS", anchor_published_at=AS_OF, resolved_at=AS_OF)

    assert resolved.resolution_reason == REASON_TIMESTAMP_PRECEDENCE_TIEBREAK
    assert resolved.conflicting is True
    assert resolved.winning_source == "yahoo-finance"  # earliest of the tied-authority sources wins


def test_news_authoritative_source_overrides_majority(session, stock, monkeypatch):
    import app.source_authority_resolution as sar
    monkeypatch.setitem(
        sar.AUTHORITY_TIER_BY_FACT_TYPE, FACT_TYPE_NEWS_EVENT,
        {"yahoo-finance": Decimal("1"), "alpha-vantage": Decimal("1"), "finnhub": Decimal("2")},
    )
    _add_news(session, stock, source="yahoo-finance", headline="Deal falls through", published_at=AS_OF)
    _add_news(session, stock, source="alpha-vantage", headline="Deal falls through", published_at=AS_OF + timedelta(minutes=10))
    _add_news(session, stock, source="finnhub", headline="Deal confirmed and signed", published_at=AS_OF + timedelta(minutes=20))

    resolved = resolve_news_event_fact(session, stock_id=stock.id, event_type="EARNINGS", anchor_published_at=AS_OF, resolved_at=AS_OF)

    assert resolved.resolution_reason == REASON_AUTHORITATIVE_SOURCE_OVERRIDE
    assert resolved.winning_source == "finnhub"
    assert resolved.resolved_value_text == "Deal confirmed and signed"


def test_news_idempotent(session, stock):
    _add_news(session, stock, source="yahoo-finance", headline="Q3 earnings beat estimates")

    fact_key = f"EARNINGS:{AS_OF.isoformat()}"
    first = resolve_news_event_fact(session, stock_id=stock.id, event_type="EARNINGS", anchor_published_at=AS_OF, resolved_at=AS_OF)
    second = resolve_news_event_fact(session, stock_id=stock.id, event_type="EARNINGS", anchor_published_at=AS_OF, resolved_at=AS_OF)

    assert first.id == second.id
    assert len(get_resolved_fact_history(session, fact_type=FACT_TYPE_NEWS_EVENT, stock_id=stock.id, fact_key=fact_key)) == 1
