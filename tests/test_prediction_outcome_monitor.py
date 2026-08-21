from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.evidence_snapshot import EVIDENCE_CATEGORY_NEWS, STATUS_AVAILABLE
from app.models import MarketPrice, Prediction, RecommendationEvidenceItem, Stock
from app.prediction_outcome_monitor import (
    MONITOR_RULE_VERSION,
    STATE_DATA_UNRESOLVED,
    STATE_HORIZON_EXPIRED,
    STATE_INVALIDATED,
    STATE_STOP_LOSS_HIT,
    STATE_TARGET_HIT,
    PredictionOutcomeEventImmutableError,
    detect_material_movement,
    evaluate_prediction_realtime,
    get_event_history,
    get_terminal_event,
)
from app.recommendations import record_recommendation
from app.target_stop_loss import publish_recommendation

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


def make_prediction(session, stock, *, horizon_days=5, entry_price="100", target_return="0.05", stop_return="-0.03"):
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
        consensus_contract_version="c1",
        horizon_selection_version="h1",
        scoring_contract_version="s1",
        opportunity_score=Decimal("60.00"),
    )


def add_bar(session, stock_id, *, day_offset, close, high=None, low=None, source="yahoo"):
    close = Decimal(str(close))
    session.add(
        MarketPrice(
            stock_id=stock_id,
            timestamp=AS_OF + timedelta(days=day_offset),
            open=close,
            high=Decimal(str(high)) if high is not None else close + Decimal("0.5"),
            low=Decimal(str(low)) if low is not None else close - Decimal("0.5"),
            close=close,
            volume=1000,
            source=source,
        )
    )
    session.flush()


def test_target_hit_detected_before_full_horizon_elapses(session):
    stock = make_stock(session)
    prediction = make_prediction(session, stock, horizon_days=5, entry_price="100", target_return="0.05")
    # Only 1 of 5 horizon days has a bar -- M1.5's evaluate_recommendation
    # would refuse to evaluate at all here; this monitor must not wait.
    add_bar(session, stock.id, day_offset=1, close=104, high=106)

    result = evaluate_prediction_realtime(session, prediction, as_of=AS_OF + timedelta(days=1))

    assert result.state == STATE_TARGET_HIT
    assert result.observed_price == Decimal("105.000000")
    assert result.provider == "yahoo"
    assert result.monitor_rule_version == MONITOR_RULE_VERSION


def test_stop_loss_checked_before_target_on_same_bar(session):
    stock = make_stock(session)
    prediction = make_prediction(session, stock, horizon_days=5, entry_price="100", target_return="0.05", stop_return="-0.03")
    add_bar(session, stock.id, day_offset=1, close=100, high=108, low=90)

    result = evaluate_prediction_realtime(session, prediction, as_of=AS_OF + timedelta(days=1))

    assert result.state == STATE_STOP_LOSS_HIT
    assert result.observed_price == Decimal("97.000000")


def test_horizon_expires_when_no_hit_after_horizon_days_of_bars(session):
    stock = make_stock(session)
    prediction = make_prediction(session, stock, horizon_days=3, entry_price="100", target_return="0.05", stop_return="-0.03")
    add_bar(session, stock.id, day_offset=1, close=101)
    add_bar(session, stock.id, day_offset=2, close=101.5)
    add_bar(session, stock.id, day_offset=3, close=102)

    result = evaluate_prediction_realtime(session, prediction, as_of=AS_OF + timedelta(days=3))

    assert result.state == STATE_HORIZON_EXPIRED
    assert result.observed_price == Decimal("102")


def test_remains_active_mid_horizon_with_no_hit_and_fresh_data(session):
    stock = make_stock(session)
    prediction = make_prediction(session, stock, horizon_days=5, entry_price="100", target_return="0.05", stop_return="-0.03")
    add_bar(session, stock.id, day_offset=1, close=101)

    result = evaluate_prediction_realtime(session, prediction, as_of=AS_OF + timedelta(days=1))

    assert result is None
    assert get_terminal_event(session, prediction.id) is None


def test_closure_is_idempotent_and_never_re_evaluates(session):
    stock = make_stock(session)
    prediction = make_prediction(session, stock, horizon_days=5, entry_price="100", target_return="0.05")
    add_bar(session, stock.id, day_offset=1, close=104, high=106)

    first = evaluate_prediction_realtime(session, prediction, as_of=AS_OF + timedelta(days=1))
    # A later bar that would also "hit" must never produce a second event.
    add_bar(session, stock.id, day_offset=2, close=110, high=112)
    second = evaluate_prediction_realtime(session, prediction, as_of=AS_OF + timedelta(days=2))

    assert second.id == first.id
    assert len(get_event_history(session, prediction.id)) == 1


def test_stale_price_data_during_trading_session_is_flagged_not_silently_closed(session):
    stock = make_stock(session)
    prediction = make_prediction(session, stock, horizon_days=7, entry_price="100", target_return="0.05", stop_return="-0.03")
    # Newest bar is far behind `as_of`, which itself falls in a live trading session.
    add_bar(session, stock.id, day_offset=1, close=101)
    as_of = datetime(2026, 8, 17, 5, 0, tzinfo=timezone.utc)  # Monday, 10:30 IST -- market hours

    result = evaluate_prediction_realtime(session, prediction, as_of=as_of)

    assert result.state == STATE_DATA_UNRESOLVED
    assert get_terminal_event(session, prediction.id) is None

    # Re-polling with no new evidence must not duplicate the same gap.
    result2 = evaluate_prediction_realtime(session, prediction, as_of=as_of + timedelta(minutes=15))
    assert result2 is None
    assert len(get_event_history(session, prediction.id)) == 1


def test_material_assumption_decay_closes_as_invalidated(session):
    stock = make_stock(session)
    prediction = make_prediction(session, stock, horizon_days=5, entry_price="100", target_return="0.05", stop_return="-0.03")
    session.add(RecommendationEvidenceItem(
        prediction_id=prediction.id, evidence_category=EVIDENCE_CATEGORY_NEWS, status=STATUS_AVAILABLE, source="test",
        reference=None, evidence_timestamp=AS_OF - timedelta(hours=12), is_stale=False, snapshot_rule_version="EVS-001",
        captured_at=AS_OF,
    ))
    session.commit()
    # No price bars at all -- invalidation must be detected before any price check.

    result = evaluate_prediction_realtime(session, prediction, as_of=AS_OF + timedelta(hours=13))

    assert result.state == STATE_INVALIDATED
    assert get_terminal_event(session, prediction.id) is not None


def test_uses_published_absolute_prices_when_available(session):
    stock = make_stock(session)
    prediction = make_prediction(session, stock, horizon_days=5, entry_price="100", target_return="0.05", stop_return="-0.03")
    publish_recommendation(session, prediction, published_at=AS_OF)
    add_bar(session, stock.id, day_offset=1, close=104, high=105.5)

    result = evaluate_prediction_realtime(session, prediction, as_of=AS_OF + timedelta(days=1))

    assert result.state == STATE_TARGET_HIT
    assert result.observed_price == Decimal("105.000000")
    assert "TSL-001" in result.prediction_version


def test_event_rows_are_fully_immutable(session):
    stock = make_stock(session)
    prediction = make_prediction(session, stock, horizon_days=5, entry_price="100", target_return="0.05")
    add_bar(session, stock.id, day_offset=1, close=104, high=106)
    event = evaluate_prediction_realtime(session, prediction, as_of=AS_OF + timedelta(days=1))

    event.observed_price = Decimal("999")
    with pytest.raises(PredictionOutcomeEventImmutableError):
        session.commit()
    session.rollback()


def test_detect_material_movement_signal():
    entry, target, stop = Decimal("100"), Decimal("105"), Decimal("97")
    assert detect_material_movement(entry, target, stop, Decimal("103.5")) is True  # 70% of the way to target
    assert detect_material_movement(entry, target, stop, Decimal("101")) is False
    assert detect_material_movement(entry, target, stop, Decimal("98.2")) is True  # 60% of the way to stop
