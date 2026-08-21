from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MarketPrice, Prediction, PredictionOutcome, Stock
from app.outcomes import (
    LABEL_HORIZON_EXPIRY,
    LABEL_INVALIDATED,
    LABEL_METHODOLOGY_VERSION,
    LABEL_STOP_LOSS_HIT,
    LABEL_TARGET_HIT,
    OutcomeImmutableError,
    classify_label_category,
    evaluate_recommendation,
)
from app.recommendations import VALID_HORIZON_DAYS, record_recommendation
from app.short_horizon_probability import SUPPORTED_HORIZON_DAYS

AS_OF = datetime(2027, 3, 1, tzinfo=timezone.utc)


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


def make_recommendation(session, stock, *, horizon_days=3, entry_price="100", target_return="0.05", stop_return="-0.03"):
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
        consensus_contract_version="PCC-001",
        horizon_selection_version="PHS-001",
        scoring_contract_version="POS-001",
        opportunity_score=Decimal("70.00"),
    )


def test_new_outcome_records_label_methodology_version(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1)
    make_prices(session, stock.id, [101])

    outcome = evaluate_recommendation(session, rec)

    assert outcome.label_methodology_version == LABEL_METHODOLOGY_VERSION


def test_label_methodology_version_is_immutable(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1)
    make_prices(session, stock.id, [101])
    outcome = evaluate_recommendation(session, rec)

    outcome.label_methodology_version = "SOME-OTHER-VERSION"
    with pytest.raises(OutcomeImmutableError):
        session.flush()
    session.rollback()


def test_a_methodology_version_bump_never_rewrites_history(session, monkeypatch):
    stock = make_stock(session)
    rec_one = make_recommendation(session, stock, horizon_days=1)
    make_prices(session, stock.id, [101], start=AS_OF)
    outcome_one = evaluate_recommendation(session, rec_one)
    original_version = outcome_one.label_methodology_version

    import app.outcomes as outcomes_module
    monkeypatch.setattr(outcomes_module, "LABEL_METHODOLOGY_VERSION", "LBL-002")

    rec_two = make_recommendation(session, stock, horizon_days=1)
    make_prices(session, stock.id, [101], start=AS_OF + timedelta(days=10))
    outcome_two = evaluate_recommendation(session, rec_two)

    assert outcome_one.label_methodology_version == original_version
    assert outcome_two.label_methodology_version == "LBL-002"


def test_classify_label_category_target_hit():
    outcome = PredictionOutcome(
        prediction_id=1, evaluation_date=AS_OF, highest_price=Decimal("106"), lowest_price=Decimal("99"),
        closing_price=Decimal("103"), maximum_return=Decimal("0.06"), maximum_drawdown=Decimal("-0.01"),
        actual_return=Decimal("0.05"), prediction_error=Decimal("0"), target_hit=True, stop_hit=False,
        outcome="SUCCESS", label_methodology_version=LABEL_METHODOLOGY_VERSION,
    )
    assert classify_label_category(outcome) == LABEL_TARGET_HIT


def test_classify_label_category_stop_loss_hit():
    outcome = PredictionOutcome(
        prediction_id=1, evaluation_date=AS_OF, highest_price=Decimal("101"), lowest_price=Decimal("94"),
        closing_price=Decimal("98"), maximum_return=Decimal("0.01"), maximum_drawdown=Decimal("-0.06"),
        actual_return=Decimal("-0.03"), prediction_error=Decimal("-0.08"), target_hit=False, stop_hit=True,
        outcome="FAILURE", label_methodology_version=LABEL_METHODOLOGY_VERSION,
    )
    assert classify_label_category(outcome) == LABEL_STOP_LOSS_HIT


def test_classify_label_category_horizon_expiry_covers_both_signs():
    win = PredictionOutcome(
        prediction_id=1, evaluation_date=AS_OF, highest_price=Decimal("101.5"), lowest_price=Decimal("99.5"),
        closing_price=Decimal("101.5"), maximum_return=Decimal("0.015"), maximum_drawdown=Decimal("-0.005"),
        actual_return=Decimal("0.015"), prediction_error=Decimal("-0.035"), target_hit=False, stop_hit=False,
        outcome="SUCCESS", label_methodology_version=LABEL_METHODOLOGY_VERSION,
    )
    loss = PredictionOutcome(
        prediction_id=1, evaluation_date=AS_OF, highest_price=Decimal("100.5"), lowest_price=Decimal("98.5"),
        closing_price=Decimal("98.5"), maximum_return=Decimal("0.005"), maximum_drawdown=Decimal("-0.015"),
        actual_return=Decimal("-0.015"), prediction_error=Decimal("-0.065"), target_hit=False, stop_hit=False,
        outcome="FAILURE", label_methodology_version=LABEL_METHODOLOGY_VERSION,
    )
    assert classify_label_category(win) == LABEL_HORIZON_EXPIRY
    assert classify_label_category(loss) == LABEL_HORIZON_EXPIRY


def test_classify_label_category_invalidated(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=3)
    make_prices(session, stock.id, [100, 101, 102], valid=False)

    outcome = evaluate_recommendation(session, rec)

    assert outcome.outcome == "UNEVALUABLE"
    assert classify_label_category(outcome) == LABEL_INVALIDATED


def test_classification_is_deterministic_and_reproducible(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=3, entry_price="100", target_return="0.05", stop_return="-0.03")
    make_prices(session, stock.id, [101, 106, 103])
    outcome = evaluate_recommendation(session, rec)

    first = classify_label_category(outcome)
    second = classify_label_category(outcome)

    assert first == second == LABEL_TARGET_HIT


def test_same_day_ambiguity_is_deterministic_stop_first(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1, entry_price="100", target_return="0.05", stop_return="-0.03")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("100"), high=Decimal("110"), low=Decimal("90"), close=Decimal("100"),
        volume=1000, source="test",
    ))
    session.flush()

    outcome = evaluate_recommendation(session, rec)

    assert classify_label_category(outcome) == LABEL_STOP_LOSS_HIT


def test_leakage_boundary_price_beyond_horizon_never_used(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1, entry_price="100", target_return="0.05", stop_return="-0.03")
    # Within the 1-day horizon, price never reaches target/stop.
    make_prices(session, stock.id, [100.5])
    # Beyond the horizon: a huge spike that would hit target if leaked in.
    make_prices(session, stock.id, [200], start=AS_OF + timedelta(days=1))

    outcome = evaluate_recommendation(session, rec)

    assert outcome.target_hit is False
    assert classify_label_category(outcome) == LABEL_HORIZON_EXPIRY


def test_label_contract_horizon_vocabulary_is_a_documented_superset():
    """M1.95's own label contract names 1/2/3/5/7 (scope), matching
    M1.75's `SUPPORTED_HORIZON_DAYS` exactly; `VALID_HORIZON_DAYS` (M1.10)
    is honestly a subset -- day 2 is never actually produced by this
    platform's horizon-selection logic today, and this EPIC does not
    change that (see module docstrings for the established, documented
    reasoning)."""
    assert SUPPORTED_HORIZON_DAYS == (1, 2, 3, 5, 7)
    assert set(VALID_HORIZON_DAYS).issubset(set(SUPPORTED_HORIZON_DAYS))
