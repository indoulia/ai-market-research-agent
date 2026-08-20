from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MarketPrice, Stock
from app.outcomes import (
    OutcomeImmutableError,
    RecommendationAlreadyEvaluatedError,
    evaluate_recommendation,
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
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, created_at=now, updated_at=now)
    session.add(stock)
    session.flush()
    return stock


def make_prices(session, stock_id, closes, *, start=AS_OF, valid=True):
    for offset, close in enumerate(closes, start=1):
        close = Decimal(str(close))
        session.add(
            MarketPrice(
                stock_id=stock_id,
                timestamp=start + timedelta(days=offset),
                open=close if valid else Decimal("0"),
                high=close + Decimal("1") if valid else Decimal("-5"),
                low=close - Decimal("1") if valid else Decimal("999"),
                close=close,
                volume=1000 if valid else 0,
                source="test",
            )
        )
    session.flush()


def make_recommendation(session, stock, *, horizon_days=5, entry_price="100", target_return="0.05", stop_return="-0.03"):
    return record_recommendation(
        session,
        stock_id=stock.id,
        as_of_timestamp=AS_OF,
        entry_price=Decimal(entry_price),
        horizon_days=horizon_days,
        target_return=Decimal(target_return),
        stop_return=Decimal(stop_return),
        predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"),
        model_version="m1-baseline-1",
        feature_version="f1",
    )


@pytest.mark.parametrize("horizon_days", [1, 3, 5, 7])
def test_evaluates_at_correct_trading_day_horizon(session, horizon_days):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=horizon_days)
    # exactly horizon_days sessions of flat closes, plus extra sessions the evaluator must ignore
    make_prices(session, stock.id, [100] * (horizon_days + 3))

    outcome = evaluate_recommendation(session, rec)

    assert outcome is not None
    expected_last_session = AS_OF + timedelta(days=horizon_days)
    # sqlite drops tzinfo on DateTime(timezone=True) round-trips; compare naively.
    assert outcome.evaluation_date.replace(tzinfo=None) == expected_last_session.replace(tzinfo=None)


def test_returns_none_when_horizon_not_yet_elapsed(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=5)
    make_prices(session, stock.id, [100, 100, 100])  # only 3 of 5 sessions available

    assert evaluate_recommendation(session, rec) is None


def test_target_hit_classifies_success_with_exact_actual_return(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=3, entry_price="100", target_return="0.05", stop_return="-0.03")
    make_prices(session, stock.id, [101, 106, 103])  # day 2 high = 107 >= target price 105

    outcome = evaluate_recommendation(session, rec)

    assert outcome.outcome == "SUCCESS"
    assert outcome.target_hit is True
    assert outcome.stop_hit is False
    assert outcome.actual_return == Decimal("0.05")
    assert outcome.prediction_error == Decimal("0")


def test_stop_hit_classifies_failure_with_exact_actual_return(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=3, entry_price="100", target_return="0.05", stop_return="-0.03")
    make_prices(session, stock.id, [99, 95, 98])  # day 2 low = 94 <= stop price 97

    outcome = evaluate_recommendation(session, rec)

    assert outcome.outcome == "FAILURE"
    assert outcome.stop_hit is True
    assert outcome.target_hit is False
    assert outcome.actual_return == Decimal("-0.03")


def test_stop_checked_before_target_on_same_day(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1, entry_price="100", target_return="0.05", stop_return="-0.03")
    # single day where both thresholds are technically breached (high >= 105, low <= 97)
    session.add(
        MarketPrice(
            stock_id=stock.id,
            timestamp=AS_OF + timedelta(days=1),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("100"),
            volume=1000,
            source="test",
        )
    )
    session.flush()

    outcome = evaluate_recommendation(session, rec)

    assert outcome.outcome == "FAILURE"
    assert outcome.stop_hit is True
    assert outcome.target_hit is False


def test_no_threshold_hit_uses_closing_return_sign(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=3, entry_price="100", target_return="0.05", stop_return="-0.03")
    make_prices(session, stock.id, [100.5, 101, 101.5])  # never reaches 105 or drops to 97

    outcome = evaluate_recommendation(session, rec)

    assert outcome.outcome == "SUCCESS"
    assert outcome.target_hit is False
    assert outcome.stop_hit is False
    assert outcome.actual_return == (Decimal("101.5") - Decimal("100")) / Decimal("100")


def test_invalid_price_data_in_window_is_unevaluable(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=3)
    make_prices(session, stock.id, [100, 101, 102], valid=False)

    outcome = evaluate_recommendation(session, rec)

    assert outcome.outcome == "UNEVALUABLE"


def test_prediction_status_transitions_to_evaluated(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1)
    make_prices(session, stock.id, [101])

    assert rec.status == "OPEN"
    evaluate_recommendation(session, rec)
    assert rec.status == "EVALUATED"


def test_cannot_evaluate_the_same_recommendation_twice(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1)
    make_prices(session, stock.id, [101])

    evaluate_recommendation(session, rec)
    with pytest.raises(RecommendationAlreadyEvaluatedError):
        evaluate_recommendation(session, rec)


def test_outcome_fields_are_immutable_after_creation(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1)
    make_prices(session, stock.id, [101])
    outcome = evaluate_recommendation(session, rec)

    outcome.outcome = "SUCCESS" if outcome.outcome == "FAILURE" else "FAILURE"
    with pytest.raises(OutcomeImmutableError):
        session.flush()
    session.rollback()


def test_original_recommendation_is_unchanged_by_evaluation(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1, entry_price="100", target_return="0.05")
    make_prices(session, stock.id, [200])  # would have hit target, but entry_price must stay 100

    evaluate_recommendation(session, rec)

    assert rec.entry_price == Decimal("100")
    assert rec.target_return == Decimal("0.05")
