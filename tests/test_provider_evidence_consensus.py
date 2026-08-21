from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import FundamentalDataRecord, NewsEventRecord, Stock
from app.provider_evidence_consensus import (
    CONSENSUS_VERSION,
    NEWS_VERDICT_INDEPENDENT_CORROBORATION,
    NEWS_VERDICT_SINGLE_SOURCE,
    NEWS_VERDICT_SYNDICATED_DUPLICATE,
    VERDICT_CONSENSUS_STRONG,
    VERDICT_INSUFFICIENT_SOURCES,
    VERDICT_MATERIAL_DISAGREEMENT,
    assess_fundamental_consensus,
    classify_news_event_consensus,
    get_fundamental_consensus_history,
)

AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
PERIOD_END = date(2026, 12, 31)


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


def test_insufficient_sources_with_only_one_provider(session, stock):
    _add_fundamental(session, stock, source="yahoo-finance", eps=Decimal("5.00"))

    assessment = assess_fundamental_consensus(session, stock_id=stock.id, period_end_date=PERIOD_END, evaluated_at=AS_OF)

    assert assessment.verdict == VERDICT_INSUFFICIENT_SOURCES
    assert assessment.source_count == 1
    assert assessment.weighted_mean is None
    assert assessment.consensus_rule_version == CONSENSUS_VERSION


def test_strong_consensus_when_providers_agree(session, stock):
    _add_fundamental(session, stock, source="yahoo-finance", eps=Decimal("5.00"))
    _add_fundamental(session, stock, source="alpha-vantage", eps=Decimal("5.02"))

    assessment = assess_fundamental_consensus(session, stock_id=stock.id, period_end_date=PERIOD_END, evaluated_at=AS_OF)

    assert assessment.verdict == VERDICT_CONSENSUS_STRONG
    assert assessment.source_count == 2
    assert assessment.trust_reduction_recommended is False


def test_material_disagreement_when_providers_diverge(session, stock):
    _add_fundamental(session, stock, source="yahoo-finance", eps=Decimal("5.00"))
    _add_fundamental(session, stock, source="alpha-vantage", eps=Decimal("2.00"))

    assessment = assess_fundamental_consensus(session, stock_id=stock.id, period_end_date=PERIOD_END, evaluated_at=AS_OF)

    assert assessment.verdict == VERDICT_MATERIAL_DISAGREEMENT
    assert assessment.trust_reduction_recommended is True


def test_dedupes_to_latest_fetch_per_source(session, stock):
    _add_fundamental(session, stock, source="yahoo-finance", eps=Decimal("1.00"), fetched_at=AS_OF - timedelta(days=10))
    _add_fundamental(session, stock, source="yahoo-finance", eps=Decimal("5.00"), fetched_at=AS_OF)

    assessment = assess_fundamental_consensus(session, stock_id=stock.id, period_end_date=PERIOD_END, evaluated_at=AS_OF)

    # Still only ONE distinct source after dedup -- re-fetching never inflates source_count.
    assert assessment.source_count == 1
    assert assessment.verdict == VERDICT_INSUFFICIENT_SOURCES


def test_fundamental_consensus_idempotent(session, stock):
    _add_fundamental(session, stock, source="yahoo-finance", eps=Decimal("5.00"))
    _add_fundamental(session, stock, source="alpha-vantage", eps=Decimal("5.02"))

    first = assess_fundamental_consensus(session, stock_id=stock.id, period_end_date=PERIOD_END, evaluated_at=AS_OF)
    second = assess_fundamental_consensus(session, stock_id=stock.id, period_end_date=PERIOD_END, evaluated_at=AS_OF)

    assert first.id == second.id
    assert len(get_fundamental_consensus_history(session, stock_id=stock.id, period_end_date=PERIOD_END)) == 1


def _add_news(session, stock, *, source, headline, event_type="EARNINGS", published_at=AS_OF, external_id=None):
    session.add(NewsEventRecord(
        stock_id=stock.id, source=source, external_id=external_id or f"{source}-{headline}-{published_at.isoformat()}",
        headline=headline, event_type=event_type, materiality="MEDIUM", published_at=published_at,
        fetched_at=published_at, ingestion_rule_version="NEI-001",
    ))
    session.commit()


def test_news_single_source(session, stock):
    _add_news(session, stock, source="yahoo-finance", headline="Q3 earnings beat estimates")

    assessment = classify_news_event_consensus(
        session, stock_id=stock.id, event_type="EARNINGS", anchor_published_at=AS_OF, evaluated_at=AS_OF,
    )

    assert assessment.verdict == NEWS_VERDICT_SINGLE_SOURCE
    assert assessment.distinct_source_count == 1


def test_news_syndicated_duplicate_same_headline(session, stock):
    _add_news(session, stock, source="yahoo-finance", headline="Q3 earnings beat estimates", published_at=AS_OF)
    _add_news(session, stock, source="finnhub", headline="Q3 EARNINGS BEAT ESTIMATES", published_at=AS_OF + timedelta(minutes=5))

    assessment = classify_news_event_consensus(
        session, stock_id=stock.id, event_type="EARNINGS", anchor_published_at=AS_OF, evaluated_at=AS_OF,
    )

    assert assessment.verdict == NEWS_VERDICT_SYNDICATED_DUPLICATE
    assert assessment.distinct_source_count == 2
    assert assessment.distinct_headline_count == 1


def test_news_independent_corroboration_different_headlines(session, stock):
    _add_news(session, stock, source="yahoo-finance", headline="Q3 earnings beat estimates", published_at=AS_OF)
    _add_news(session, stock, source="finnhub", headline="Company raises full-year guidance after strong Q3", published_at=AS_OF + timedelta(hours=1))

    assessment = classify_news_event_consensus(
        session, stock_id=stock.id, event_type="EARNINGS", anchor_published_at=AS_OF, evaluated_at=AS_OF,
    )

    assert assessment.verdict == NEWS_VERDICT_INDEPENDENT_CORROBORATION
    assert assessment.distinct_headline_count == 2


def test_news_outside_syndication_window_excluded(session, stock):
    _add_news(session, stock, source="yahoo-finance", headline="Q3 earnings beat estimates", published_at=AS_OF)
    _add_news(session, stock, source="finnhub", headline="Company raises full-year guidance", published_at=AS_OF + timedelta(days=3))

    assessment = classify_news_event_consensus(
        session, stock_id=stock.id, event_type="EARNINGS", anchor_published_at=AS_OF, evaluated_at=AS_OF,
        syndication_window=timedelta(hours=6),
    )

    assert assessment.distinct_source_count == 1
    assert assessment.verdict == NEWS_VERDICT_SINGLE_SOURCE
