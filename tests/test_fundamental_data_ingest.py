from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.fundamental_data.ingest import (
    FAILURE_NO_DATA_RETURNED,
    FUNDAMENTAL_INGESTION_VERSION,
    FundamentalDataRecordImmutableError,
    get_latest_fundamental_record,
    ingest_fundamental_data,
)
from app.fundamental_data.yahoo import RawFundamentals
from app.models import DataFetchAttempt, FundamentalDataRecord, Stock
from app.refresh_policy import DATA_TYPE_FUNDAMENTAL

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

    def __init__(self, raw=None, error=None):
        self.raw = raw
        self.error = error
        self.calls = 0

    def fetch_fundamentals(self, symbol):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.raw


def _raw(**overrides):
    defaults = dict(
        period_end_date=None, revenue=Decimal("100"), net_income=Decimal("10"), eps=Decimal("1.5"),
        gross_margin=Decimal("0.4"), operating_margin=Decimal("0.2"), net_margin=Decimal("0.1"),
        debt_to_equity=Decimal("0.5"), free_cash_flow=Decimal("20"), pe_ratio=Decimal("15"),
        price_to_book=Decimal("3"),
    )
    defaults.update(overrides)
    return RawFundamentals(**defaults)


def test_successful_ingestion_persists_record_and_fetch_attempt(session):
    stock = _make_stock(session)
    provider = _FakeProvider(raw=_raw())

    record = ingest_fundamental_data(session, provider, stock, requested_at=T0)

    assert record is not None
    assert record.stock_id == stock.id
    assert record.source == "fake-provider"
    assert record.revenue == Decimal("100")
    assert record.ingestion_rule_version == FUNDAMENTAL_INGESTION_VERSION
    assert record.published_at.replace(tzinfo=timezone.utc) == T0  # no period_end_date -> honest fallback to fetch time

    attempts = session.query(DataFetchAttempt).filter_by(data_type=DATA_TYPE_FUNDAMENTAL).all()
    assert len(attempts) == 1
    assert attempts[0].success is True


def test_no_data_returned_records_failed_attempt_and_no_row(session):
    stock = _make_stock(session)
    provider = _FakeProvider(raw=None)

    record = ingest_fundamental_data(session, provider, stock, requested_at=T0)

    assert record is None
    assert session.query(FundamentalDataRecord).count() == 0
    attempt = session.query(DataFetchAttempt).filter_by(data_type=DATA_TYPE_FUNDAMENTAL).one()
    assert attempt.success is False
    assert attempt.failure_reason == FAILURE_NO_DATA_RETURNED


def test_provider_error_records_failed_attempt_and_no_row(session):
    stock = _make_stock(session)
    provider = _FakeProvider(error=RuntimeError("rate limited"))

    record = ingest_fundamental_data(session, provider, stock, requested_at=T0)

    assert record is None
    assert session.query(FundamentalDataRecord).count() == 0
    attempt = session.query(DataFetchAttempt).filter_by(data_type=DATA_TYPE_FUNDAMENTAL).one()
    assert attempt.success is False
    assert "rate limited" in attempt.failure_reason


def test_fresh_existing_data_skips_provider_call(session):
    stock = _make_stock(session)
    provider = _FakeProvider(raw=_raw())
    ingest_fundamental_data(session, provider, stock, requested_at=T0)
    assert provider.calls == 1

    second = ingest_fundamental_data(session, provider, stock, requested_at=T0 + timedelta(days=1))

    assert provider.calls == 1  # provider not called again -- still fresh under the 90-day policy
    assert second is not None
    assert session.query(FundamentalDataRecord).count() == 1


def test_stale_existing_data_triggers_a_new_fetch(session):
    stock = _make_stock(session)
    provider = _FakeProvider(raw=_raw(revenue=Decimal("100")))
    ingest_fundamental_data(session, provider, stock, requested_at=T0)

    provider.raw = _raw(revenue=Decimal("200"))
    second = ingest_fundamental_data(session, provider, stock, requested_at=T0 + timedelta(days=100))

    assert provider.calls == 2
    assert second.revenue == Decimal("200")
    assert session.query(FundamentalDataRecord).count() == 2


def test_point_in_time_safety_hides_future_revisions(session):
    stock = _make_stock(session)
    old = FundamentalDataRecord(
        stock_id=stock.id, source="test", period_end_date=None, revenue=Decimal("100"), net_income=None,
        eps=None, gross_margin=None, operating_margin=None, net_margin=None, debt_to_equity=None,
        free_cash_flow=None, pe_ratio=None, price_to_book=None,
        published_at=T0, fetched_at=T0, ingestion_rule_version=FUNDAMENTAL_INGESTION_VERSION,
    )
    revised = FundamentalDataRecord(
        stock_id=stock.id, source="test", period_end_date=None, revenue=Decimal("999"), net_income=None,
        eps=None, gross_margin=None, operating_margin=None, net_margin=None, debt_to_equity=None,
        free_cash_flow=None, pe_ratio=None, price_to_book=None,
        published_at=T0 + timedelta(days=200), fetched_at=T0 + timedelta(days=200),
        ingestion_rule_version=FUNDAMENTAL_INGESTION_VERSION,
    )
    session.add_all([old, revised])
    session.commit()

    as_of_before_revision = get_latest_fundamental_record(session, stock.id, as_of_timestamp=T0 + timedelta(days=10))
    as_of_after_revision = get_latest_fundamental_record(session, stock.id, as_of_timestamp=T0 + timedelta(days=250))

    assert as_of_before_revision.revenue == Decimal("100")
    assert as_of_after_revision.revenue == Decimal("999")


def test_fundamental_data_record_is_immutable(session):
    stock = _make_stock(session)
    provider = _FakeProvider(raw=_raw())
    record = ingest_fundamental_data(session, provider, stock, requested_at=T0)

    record.revenue = Decimal("999999")
    with pytest.raises(FundamentalDataRecordImmutableError):
        session.commit()
    session.rollback()
