from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MarketPrice, Stock
from app.recommendation_tracking import (
    OBSERVATION_RULE_VERSION,
    RecommendationObservationImmutableError,
    get_recommendation_tracking_history,
    record_daily_observations,
)
from app.recommendations import record_recommendation

AS_OF = datetime(2026, 8, 10, tzinfo=timezone.utc)


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


def make_stock(session, symbol="RELIANCE"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def make_prices(session, stock_id, closes, *, start=AS_OF, valid=True):
    for offset, close in enumerate(closes, start=1):
        close = Decimal(str(close))
        session.add(MarketPrice(
            stock_id=stock_id,
            timestamp=start + timedelta(days=offset),
            open=close if valid else Decimal("0"),
            high=close + Decimal("1") if valid else Decimal("-5"),
            low=close - Decimal("1") if valid else Decimal("999"),
            close=close,
            volume=1000 if valid else 0,
            source="test",
        ))
    session.flush()


def make_recommendation(session, stock, *, horizon_days=5, entry_price="100"):
    return record_recommendation(
        session,
        stock_id=stock.id,
        as_of_timestamp=AS_OF,
        entry_price=Decimal(entry_price),
        horizon_days=horizon_days,
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
        predicted_probability=Decimal("0.70"),
        confidence=Decimal("0.80"),
        model_version="m1-baseline-1",
        feature_version="f1",
        consensus_contract_version="PCC-001",
        horizon_selection_version="PHS-001",
        scoring_contract_version="POS-001",
        opportunity_score=Decimal("70.00"),
    )


def test_full_horizon_produces_one_observation_per_day(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=5)
    make_prices(session, stock.id, [101, 102, 103, 104, 105])

    observations = record_daily_observations(session, rec)

    assert len(observations) == 5
    assert [o.day_number for o in observations] == [1, 2, 3, 4, 5]
    assert observations[-1].horizon_complete is True
    assert all(not o.horizon_complete for o in observations[:-1])
    assert observations[0].close_price == Decimal("101")
    assert observations[0].return_since_entry == Decimal("0.01")
    assert observations[0].observation_rule_version == OBSERVATION_RULE_VERSION


def test_partial_data_only_observes_available_days(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=5)
    make_prices(session, stock.id, [101, 102])  # only 2 of 5 sessions so far

    observations = record_daily_observations(session, rec)

    assert len(observations) == 2
    assert all(not o.horizon_complete for o in observations)


def test_resuming_adds_only_new_days_without_touching_prior_ones(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=5)
    make_prices(session, stock.id, [101, 102])

    first_pass = record_daily_observations(session, rec)
    assert len(first_pass) == 2

    make_prices(session, stock.id, [103, 104, 105], start=AS_OF + timedelta(days=2))
    second_pass = record_daily_observations(session, rec)

    assert len(second_pass) == 3
    assert [o.day_number for o in second_pass] == [3, 4, 5]
    assert second_pass[-1].horizon_complete is True

    full_history = get_recommendation_tracking_history(session, rec.id)
    assert len(full_history) == 5
    assert [o.day_number for o in full_history] == [1, 2, 3, 4, 5]


def test_never_observes_beyond_the_horizon(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=3)
    make_prices(session, stock.id, [101, 102, 103, 104, 105])  # 5 sessions, horizon is only 3

    observations = record_daily_observations(session, rec)

    assert len(observations) == 3
    assert observations[-1].horizon_complete is True


def test_invalid_market_data_is_recorded_as_explicitly_unavailable(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=3)
    make_prices(session, stock.id, [101], valid=True)
    make_prices(session, stock.id, [102], start=AS_OF + timedelta(days=1), valid=False)
    make_prices(session, stock.id, [103], start=AS_OF + timedelta(days=2), valid=True)

    observations = record_daily_observations(session, rec)

    assert observations[0].data_available is True
    assert observations[1].data_available is False
    assert observations[1].close_price is None
    assert observations[1].return_since_entry is None
    assert observations[2].data_available is True


def test_observation_is_immutable_after_creation(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1)
    make_prices(session, stock.id, [101])
    (observation,) = record_daily_observations(session, rec)

    observation.close_price = Decimal("999")
    with pytest.raises(RecommendationObservationImmutableError, match="close_price"):
        session.flush()
    session.rollback()


def test_tracking_history_reconstructs_a_completed_recommendation(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=3)
    make_prices(session, stock.id, [101, 102, 103])
    record_daily_observations(session, rec)

    history = get_recommendation_tracking_history(session, rec.id)

    assert [o.day_number for o in history] == [1, 2, 3]
    assert [float(o.close_price) for o in history] == [101.0, 102.0, 103.0]
    assert history[-1].horizon_complete is True
