from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DataFetchAttempt, MarketPrice, Stock
from app.refresh_policy import (
    DATA_TYPE_FUNDAMENTAL,
    DATA_TYPE_MARKET,
    DATA_TYPE_NEWS_EVENT,
    REASON_MISSING_DATA,
    REASON_STALE_DATA,
    REFRESH_POLICY_VERSION,
    DataFetchAttemptImmutableError,
    UnsupportedDataTypeError,
    check_market_data_freshness,
    get_fetch_history,
    is_data_fresh,
    record_fetch_attempt,
)

AS_OF = datetime(2026, 8, 21, tzinfo=timezone.utc)


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
    session.flush()
    return stock


def test_missing_source_timestamp_is_explicit_not_fabricated():
    check = is_data_fresh(DATA_TYPE_MARKET, None, AS_OF)

    assert check.is_fresh is False
    assert check.reason == REASON_MISSING_DATA
    assert check.staleness is None


def test_fresh_market_data_within_policy():
    source_timestamp = AS_OF - timedelta(hours=12)
    check = is_data_fresh(DATA_TYPE_MARKET, source_timestamp, AS_OF)

    assert check.is_fresh is True
    assert check.reason is None


def test_stale_market_data_beyond_policy():
    source_timestamp = AS_OF - timedelta(days=3)
    check = is_data_fresh(DATA_TYPE_MARKET, source_timestamp, AS_OF)

    assert check.is_fresh is False
    assert check.reason == REASON_STALE_DATA


def test_each_supported_data_type_has_a_defined_policy():
    for data_type in (DATA_TYPE_MARKET, DATA_TYPE_NEWS_EVENT, DATA_TYPE_FUNDAMENTAL):
        check = is_data_fresh(data_type, AS_OF, AS_OF)
        assert check.is_fresh is True


def test_unknown_data_type_is_rejected_explicitly():
    with pytest.raises(UnsupportedDataTypeError):
        is_data_fresh("SOCIAL_MEDIA_SENTIMENT", AS_OF, AS_OF)


def test_check_market_data_freshness_uses_the_latest_ingested_price(session):
    stock = _make_stock(session)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF - timedelta(hours=6),
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=1000, source="test",
    ))
    session.flush()

    check = check_market_data_freshness(session, stock.id, AS_OF)

    assert check.is_fresh is True
    # sqlite drops tzinfo on DateTime(timezone=True) round-trips; compare naively.
    assert check.source_timestamp.replace(tzinfo=None) == (AS_OF - timedelta(hours=6)).replace(tzinfo=None)


def test_check_market_data_freshness_with_no_data_at_all(session):
    stock = _make_stock(session)

    check = check_market_data_freshness(session, stock.id, AS_OF)

    assert check.is_fresh is False
    assert check.reason == REASON_MISSING_DATA


def test_recording_a_fetch_attempt_persists_provenance(session):
    attempt = record_fetch_attempt(
        session, data_type=DATA_TYPE_MARKET, scope_key="RELIANCE",
        requested_at=AS_OF, source_timestamp=AS_OF - timedelta(hours=1), success=True,
    )

    assert attempt.refresh_policy_version == REFRESH_POLICY_VERSION
    assert attempt.success is True
    assert attempt.failure_reason is None


def test_failed_fetch_attempts_are_recorded_explicitly(session):
    attempt = record_fetch_attempt(
        session, data_type=DATA_TYPE_MARKET, scope_key="RELIANCE",
        requested_at=AS_OF, source_timestamp=None, success=False, failure_reason="provider_timeout",
    )

    assert attempt.success is False
    assert attempt.failure_reason == "provider_timeout"


def test_duplicate_fetch_is_avoided_when_existing_data_is_already_fresh(session):
    first = record_fetch_attempt(
        session, data_type=DATA_TYPE_MARKET, scope_key="RELIANCE",
        requested_at=AS_OF - timedelta(hours=2), source_timestamp=AS_OF - timedelta(hours=3), success=True,
    )

    second = record_fetch_attempt(
        session, data_type=DATA_TYPE_MARKET, scope_key="RELIANCE",
        requested_at=AS_OF, source_timestamp=AS_OF, success=True,
    )

    assert first.id == second.id
    assert session.query(DataFetchAttempt).count() == 1


def test_stale_existing_data_triggers_a_new_recorded_fetch(session):
    record_fetch_attempt(
        session, data_type=DATA_TYPE_MARKET, scope_key="RELIANCE",
        requested_at=AS_OF - timedelta(days=5), source_timestamp=AS_OF - timedelta(days=5), success=True,
    )

    second = record_fetch_attempt(
        session, data_type=DATA_TYPE_MARKET, scope_key="RELIANCE",
        requested_at=AS_OF, source_timestamp=AS_OF, success=True,
    )

    assert session.query(DataFetchAttempt).count() == 2
    assert second.source_timestamp.replace(tzinfo=None) == AS_OF.replace(tzinfo=None)


def test_fetch_attempt_is_immutable_after_creation(session):
    attempt = record_fetch_attempt(
        session, data_type=DATA_TYPE_MARKET, scope_key="RELIANCE",
        requested_at=AS_OF, source_timestamp=AS_OF, success=True,
    )

    attempt.success = False
    with pytest.raises(DataFetchAttemptImmutableError, match="success"):
        session.flush()
    session.rollback()


def test_get_fetch_history_returns_the_full_ordered_sequence(session):
    record_fetch_attempt(
        session, data_type=DATA_TYPE_MARKET, scope_key="RELIANCE",
        requested_at=AS_OF - timedelta(days=5), source_timestamp=AS_OF - timedelta(days=5), success=True,
    )
    record_fetch_attempt(
        session, data_type=DATA_TYPE_MARKET, scope_key="RELIANCE",
        requested_at=AS_OF, source_timestamp=None, success=False, failure_reason="provider_error",
    )

    history = get_fetch_history(session, data_type=DATA_TYPE_MARKET, scope_key="RELIANCE")

    assert len(history) == 2
    assert history[0].success is True
    assert history[1].success is False
