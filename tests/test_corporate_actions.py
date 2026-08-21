from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.corporate_actions import (
    ACTION_BONUS,
    ACTION_DELISTING,
    ACTION_DIVIDEND,
    ACTION_SPLIT,
    ACTION_SYMBOL_CHANGE,
    CORPORATE_ACTION_VERSION,
    CorporateActionImmutableError,
    InvalidCorporateActionError,
    adjust_price,
    compute_price_adjustment_factor,
    get_corporate_actions,
    record_corporate_action,
)
from app.db import Base
from app.models import MarketPrice, Stock
from app.outcomes import evaluate_recommendation
from app.recommendations import record_recommendation, get_recommendation_history

AS_OF = datetime(2027, 4, 1, tzinfo=timezone.utc)


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


def make_recommendation(session, stock, *, horizon_days=1, entry_price="100", target_return="0.05", stop_return="-0.03"):
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


def test_split_requires_a_positive_ratio(session):
    stock = make_stock(session)
    with pytest.raises(InvalidCorporateActionError):
        record_corporate_action(
            session, stock=stock, action_type=ACTION_SPLIT, effective_date=date(2027, 4, 5),
            source="test", recorded_at=AS_OF,
        )


def test_dividend_requires_a_positive_cash_amount(session):
    stock = make_stock(session)
    with pytest.raises(InvalidCorporateActionError):
        record_corporate_action(
            session, stock=stock, action_type=ACTION_DIVIDEND, effective_date=date(2027, 4, 5),
            source="test", recorded_at=AS_OF,
        )


def test_symbol_change_requires_new_symbol(session):
    stock = make_stock(session)
    with pytest.raises(InvalidCorporateActionError):
        record_corporate_action(
            session, stock=stock, action_type=ACTION_SYMBOL_CHANGE, effective_date=date(2027, 4, 5),
            source="test", recorded_at=AS_OF,
        )


def test_unknown_action_type_is_rejected(session):
    stock = make_stock(session)
    with pytest.raises(InvalidCorporateActionError):
        record_corporate_action(
            session, stock=stock, action_type="NOT_A_REAL_ACTION", effective_date=date(2027, 4, 5),
            source="test", recorded_at=AS_OF,
        )


def test_recorded_action_carries_its_version_and_is_immutable(session):
    stock = make_stock(session)
    action = record_corporate_action(
        session, stock=stock, action_type=ACTION_SPLIT, effective_date=date(2027, 4, 5),
        ratio=Decimal("2"), source="test", recorded_at=AS_OF,
    )

    assert action.action_version == CORPORATE_ACTION_VERSION

    action.ratio = Decimal("3")
    with pytest.raises(CorporateActionImmutableError):
        session.flush()
    session.rollback()


def test_symbol_change_renames_stock_and_preserves_history(session):
    stock = make_stock(session, symbol="OLDNAME")
    action = record_corporate_action(
        session, stock=stock, action_type=ACTION_SYMBOL_CHANGE, effective_date=date(2027, 4, 5),
        new_symbol="NEWNAME", source="test", recorded_at=AS_OF,
    )

    assert stock.symbol == "NEWNAME"
    assert action.old_symbol == "OLDNAME"
    assert action.new_symbol == "NEWNAME"


def test_delisting_flips_is_active_through_a_traced_path(session):
    stock = make_stock(session)
    assert stock.is_active is True

    record_corporate_action(
        session, stock=stock, action_type=ACTION_DELISTING, effective_date=date(2027, 4, 5),
        source="test", recorded_at=AS_OF,
    )

    assert stock.is_active is False


def test_delisted_stock_predictions_remain_in_historical_query(session):
    stock = make_stock(session)
    rec = make_recommendation(session, stock)
    make_prices(session, stock.id, [101])
    evaluate_recommendation(session, rec)

    record_corporate_action(
        session, stock=stock, action_type=ACTION_DELISTING, effective_date=date(2027, 5, 1),
        source="test", recorded_at=AS_OF,
    )

    history = get_recommendation_history(session, symbol=stock.symbol)
    assert len(history) == 1
    assert history[0].id == rec.id


def test_adjustment_factor_is_one_with_no_actions(session):
    stock = make_stock(session)
    factor = compute_price_adjustment_factor(
        session, stock.id, reference_date=date(2027, 4, 1), price_date=date(2027, 4, 10)
    )
    assert factor == Decimal("1")


def test_adjustment_factor_is_one_when_price_date_not_after_reference(session):
    stock = make_stock(session)
    record_corporate_action(
        session, stock=stock, action_type=ACTION_SPLIT, effective_date=date(2027, 4, 5),
        ratio=Decimal("2"), source="test", recorded_at=AS_OF,
    )
    factor = compute_price_adjustment_factor(
        session, stock.id, reference_date=date(2027, 4, 10), price_date=date(2027, 4, 10)
    )
    assert factor == Decimal("1")


def test_adjustment_factor_applies_a_split_between_the_two_dates(session):
    stock = make_stock(session)
    record_corporate_action(
        session, stock=stock, action_type=ACTION_SPLIT, effective_date=date(2027, 4, 5),
        ratio=Decimal("2"), source="test", recorded_at=AS_OF,
    )
    factor = compute_price_adjustment_factor(
        session, stock.id, reference_date=date(2027, 4, 1), price_date=date(2027, 4, 10)
    )
    assert factor == Decimal("2")
    assert adjust_price(Decimal("500"), factor) == Decimal("1000")


def test_adjustment_factor_excludes_action_exactly_on_reference_date(session):
    stock = make_stock(session)
    record_corporate_action(
        session, stock=stock, action_type=ACTION_SPLIT, effective_date=date(2027, 4, 1),
        ratio=Decimal("2"), source="test", recorded_at=AS_OF,
    )
    factor = compute_price_adjustment_factor(
        session, stock.id, reference_date=date(2027, 4, 1), price_date=date(2027, 4, 10)
    )
    assert factor == Decimal("1")


def test_adjustment_factor_multiplies_across_sequential_actions(session):
    stock = make_stock(session)
    record_corporate_action(
        session, stock=stock, action_type=ACTION_SPLIT, effective_date=date(2027, 4, 5),
        ratio=Decimal("2"), source="test", recorded_at=AS_OF,
    )
    record_corporate_action(
        session, stock=stock, action_type=ACTION_BONUS, effective_date=date(2027, 4, 8),
        ratio=Decimal("3"), source="test", recorded_at=AS_OF,
    )
    factor = compute_price_adjustment_factor(
        session, stock.id, reference_date=date(2027, 4, 1), price_date=date(2027, 4, 10)
    )
    assert factor == Decimal("6")


def test_dividend_is_recorded_but_never_adjusts_price(session):
    stock = make_stock(session)
    record_corporate_action(
        session, stock=stock, action_type=ACTION_DIVIDEND, effective_date=date(2027, 4, 5),
        cash_amount=Decimal("5"), source="test", recorded_at=AS_OF,
    )
    factor = compute_price_adjustment_factor(
        session, stock.id, reference_date=date(2027, 4, 1), price_date=date(2027, 4, 10)
    )
    assert factor == Decimal("1")
    actions = get_corporate_actions(session, stock.id)
    assert len(actions) == 1
    assert actions[0].action_type == ACTION_DIVIDEND
    assert actions[0].cash_amount == Decimal("5")


def test_evaluate_recommendation_is_unaffected_when_no_corporate_action_recorded(session):
    """Zero-regression proof: identical scenario to the pre-M1.96
    outcome-evaluation tests produces an identical result."""
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=3, entry_price="100", target_return="0.05", stop_return="-0.03")
    make_prices(session, stock.id, [101, 106, 103])  # day 2 high = 107 >= target price 105

    outcome = evaluate_recommendation(session, rec)

    assert outcome.outcome == "SUCCESS"
    assert outcome.target_hit is True
    assert outcome.actual_return == Decimal("0.05")


def test_evaluate_recommendation_uses_split_adjusted_basis_to_detect_a_real_target_hit(session):
    """Without adjustment, a post-split raw high of 53 vs a target price of
    105 (entry 100 * 1.05) would wrongly look like a huge loss. A 2:1
    split's ratio brings 53 back to entry-day basis (106), correctly
    detecting the target was actually hit."""
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1, entry_price="100", target_return="0.05", stop_return="-0.03")
    record_corporate_action(
        session, stock=stock, action_type=ACTION_SPLIT, effective_date=AS_OF.date() + timedelta(days=1),
        ratio=Decimal("2"), source="test", recorded_at=AS_OF,
    )
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("50"), high=Decimal("53"), low=Decimal("49"), close=Decimal("51"),
        volume=1000, source="test",
    ))
    session.flush()

    outcome = evaluate_recommendation(session, rec)

    assert outcome.target_hit is True
    assert outcome.outcome == "SUCCESS"
    assert outcome.highest_price == Decimal("106")


def test_evaluate_recommendation_without_adjustment_would_have_missed_the_target_hit(session):
    """Companion proof: the same raw post-split data, with no split
    recorded, is wrongly read as a stop-loss hit -- demonstrating why the
    adjustment in the previous test is a real correctness fix, not a
    cosmetic one."""
    stock = make_stock(session)
    rec = make_recommendation(session, stock, horizon_days=1, entry_price="100", target_return="0.05", stop_return="-0.03")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("50"), high=Decimal("53"), low=Decimal("49"), close=Decimal("51"),
        volume=1000, source="test",
    ))
    session.flush()

    outcome = evaluate_recommendation(session, rec)

    assert outcome.stop_hit is True
    assert outcome.outcome == "FAILURE"
