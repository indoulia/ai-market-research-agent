from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Stock
from app.recommendations import (
    RecommendationImmutableError,
    get_recommendation_history,
    record_recommendation,
)


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


def make_stock(session, symbol: str) -> Stock:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, created_at=now, updated_at=now)
    session.add(stock)
    session.flush()
    return stock


def make_recommendation(session, stock, *, as_of, horizon_days=5, entry_price="100.00"):
    return record_recommendation(
        session,
        stock_id=stock.id,
        as_of_timestamp=as_of,
        entry_price=Decimal(entry_price),
        horizon_days=horizon_days,
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.02"),
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        model_version="m1-baseline-1",
        feature_version="f1",
        consensus_contract_version="PCC-001",
    )


def test_record_recommendation_persists_all_fields_with_unique_id(session):
    stock = make_stock(session, "RELIANCE")
    as_of = datetime(2026, 8, 17, tzinfo=timezone.utc)

    rec = make_recommendation(session, stock, as_of=as_of)

    assert rec.id is not None
    assert rec.stock_id == stock.id
    assert rec.as_of_timestamp == as_of
    assert rec.entry_price == Decimal("100.00")
    assert rec.horizon_days == 5
    assert rec.target_return == Decimal("0.05")
    assert rec.stop_return == Decimal("-0.02")
    assert rec.predicted_probability == Decimal("0.72")
    assert rec.confidence == Decimal("0.80")
    assert rec.model_version == "m1-baseline-1"
    assert rec.feature_version == "f1"
    assert rec.consensus_contract_version == "PCC-001"
    assert rec.status == "OPEN"

    rec2 = make_recommendation(session, stock, as_of=as_of)
    assert rec2.id != rec.id


def test_rejects_invalid_horizon_days(session):
    stock = make_stock(session, "RELIANCE")
    with pytest.raises(ValueError, match="horizon_days"):
        make_recommendation(session, stock, as_of=datetime(2026, 8, 17, tzinfo=timezone.utc), horizon_days=2)


def test_recommendation_history_query_by_symbol_and_time_range(session):
    reliance = make_stock(session, "RELIANCE")
    tcs = make_stock(session, "TCS")

    r1 = make_recommendation(session, reliance, as_of=datetime(2026, 8, 10, tzinfo=timezone.utc))
    r2 = make_recommendation(session, reliance, as_of=datetime(2026, 8, 17, tzinfo=timezone.utc))
    make_recommendation(session, reliance, as_of=datetime(2026, 8, 25, tzinfo=timezone.utc))
    make_recommendation(session, tcs, as_of=datetime(2026, 8, 17, tzinfo=timezone.utc))

    results = get_recommendation_history(
        session,
        symbol="RELIANCE",
        start=datetime(2026, 8, 10, tzinfo=timezone.utc),
        end=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )

    assert [r.id for r in results] == [r1.id, r2.id]


def test_immutable_fields_cannot_be_modified_after_creation(session):
    stock = make_stock(session, "RELIANCE")
    rec = make_recommendation(session, stock, as_of=datetime(2026, 8, 17, tzinfo=timezone.utc))

    rec.entry_price = Decimal("999.99")
    with pytest.raises(RecommendationImmutableError, match="entry_price"):
        session.flush()

    session.rollback()


def test_status_field_remains_mutable_for_future_outcome_evaluation(session):
    stock = make_stock(session, "RELIANCE")
    rec = make_recommendation(session, stock, as_of=datetime(2026, 8, 17, tzinfo=timezone.utc))

    rec.status = "EVALUATED"
    session.flush()

    assert rec.status == "EVALUATED"
