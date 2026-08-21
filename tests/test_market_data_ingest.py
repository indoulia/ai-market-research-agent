from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.market_data.ingest import ingest_daily_history
from app.models import DataFetchAttempt, MarketPrice, Stock
from app.refresh_policy import DATA_TYPE_MARKET

REQUESTED_AT = datetime(2026, 8, 21, tzinfo=timezone.utc)


class StubClient:
    source = "test-provider"

    def __init__(self, candles_by_instrument=None, raises_for=()):
        self._candles_by_instrument = candles_by_instrument or {}
        self._raises_for = set(raises_for)

    def fetch_daily_candles(self, instrument, from_date, to_date):
        if instrument in self._raises_for:
            raise RuntimeError(f"provider outage for {instrument}")
        return self._candles_by_instrument.get(instrument, [])


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


def _stock(session, symbol, instrument_key):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, instrument_key=instrument_key)
    session.add(stock)
    session.flush()
    return stock


def test_provider_failure_for_one_stock_does_not_abort_the_batch(session):
    healthy = _stock(session, "HEALTHY", "NSE_HEALTHY")
    broken = _stock(session, "BROKEN", "NSE_BROKEN")
    client = StubClient(
        candles_by_instrument={"NSE_HEALTHY": [["2026-08-20T00:00:00", 100, 105, 99, 104, 1000]]},
        raises_for={"NSE_BROKEN"},
    )

    inserted = ingest_daily_history(
        session, client, from_date=REQUESTED_AT.date(), to_date=REQUESTED_AT.date(), requested_at=REQUESTED_AT
    )

    assert inserted == 1
    assert session.query(MarketPrice).filter(MarketPrice.stock_id == healthy.id).count() == 1
    assert session.query(MarketPrice).filter(MarketPrice.stock_id == broken.id).count() == 0


def test_provider_failure_is_recorded_via_record_fetch_attempt(session):
    broken = _stock(session, "BROKEN", "NSE_BROKEN")
    client = StubClient(raises_for={"NSE_BROKEN"})

    ingest_daily_history(
        session, client, from_date=REQUESTED_AT.date(), to_date=REQUESTED_AT.date(), requested_at=REQUESTED_AT
    )

    attempt = session.scalar(
        select(DataFetchAttempt).where(
            DataFetchAttempt.data_type == DATA_TYPE_MARKET, DataFetchAttempt.scope_key == str(broken.id)
        )
    )
    assert attempt is not None
    assert attempt.success is False
    assert "provider outage" in attempt.failure_reason
    assert attempt.provider_id == "test-provider"


def test_successful_fetch_is_recorded_via_record_fetch_attempt(session):
    healthy = _stock(session, "HEALTHY", "NSE_HEALTHY")
    client = StubClient(candles_by_instrument={"NSE_HEALTHY": [["2026-08-20T00:00:00", 100, 105, 99, 104, 1000]]})

    ingest_daily_history(
        session, client, from_date=REQUESTED_AT.date(), to_date=REQUESTED_AT.date(), requested_at=REQUESTED_AT
    )

    attempt = session.scalar(
        select(DataFetchAttempt).where(
            DataFetchAttempt.data_type == DATA_TYPE_MARKET, DataFetchAttempt.scope_key == str(healthy.id)
        )
    )
    assert attempt is not None
    assert attempt.success is True
    # sqlite drops tzinfo on round-trip; compare naive (real Postgres preserves it)
    assert attempt.source_timestamp.replace(tzinfo=timezone.utc) == datetime(2026, 8, 20, tzinfo=timezone.utc)


def test_empty_candle_response_still_records_a_successful_attempt(session):
    """An empty list from the provider (no trading data for the window) is a
    legitimate, auditable outcome -- distinct from a raised provider exception."""
    stock = _stock(session, "QUIET", "NSE_QUIET")
    client = StubClient(candles_by_instrument={})

    ingest_daily_history(
        session, client, from_date=REQUESTED_AT.date(), to_date=REQUESTED_AT.date(), requested_at=REQUESTED_AT
    )

    attempt = session.scalar(
        select(DataFetchAttempt).where(
            DataFetchAttempt.data_type == DATA_TYPE_MARKET, DataFetchAttempt.scope_key == str(stock.id)
        )
    )
    assert attempt is not None
    assert attempt.success is True
    assert attempt.source_timestamp is None
