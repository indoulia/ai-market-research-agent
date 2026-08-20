from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import PredictionOutcome, Stock
from app.outcome_measurement import (
    MEASUREMENT_RULE_VERSION,
    NEUTRAL_RETURN_BAND,
    OUTCOME_FAILURE,
    OUTCOME_INSUFFICIENT_DATA,
    OUTCOME_NEUTRAL,
    OUTCOME_SUCCESS,
    OutcomeMeasurementImmutableError,
    get_outcome_measurement,
    measure_outcome,
)
from app.recommendations import record_recommendation

AS_OF = datetime(2026, 8, 10, tzinfo=timezone.utc)
MEASURED_AT = datetime(2026, 8, 21, tzinfo=timezone.utc)


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


def _make_prediction(session, symbol):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return record_recommendation(
        session,
        stock_id=stock.id,
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        horizon_days=3,
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


def _make_outcome(session, prediction, *, outcome, target_hit=False, stop_hit=False, actual_return=Decimal("0")):
    row = PredictionOutcome(
        prediction_id=prediction.id,
        evaluation_date=AS_OF,
        highest_price=Decimal("105"),
        lowest_price=Decimal("95"),
        closing_price=Decimal("100"),
        maximum_return=Decimal("0.05"),
        maximum_drawdown=Decimal("-0.05"),
        actual_return=actual_return,
        prediction_error=actual_return - Decimal("0.05"),
        target_hit=target_hit,
        stop_hit=stop_hit,
        outcome=outcome,
    )
    session.add(row)
    session.flush()
    return row


def test_unevaluable_outcome_is_insufficient_data(session):
    prediction = _make_prediction(session, "AAA")
    outcome = _make_outcome(session, prediction, outcome="UNEVALUABLE", actual_return=Decimal("0"))

    measurement = measure_outcome(session, outcome, measured_at=MEASURED_AT)

    assert measurement.outcome_classification == OUTCOME_INSUFFICIENT_DATA
    assert measurement.realized_return is None
    assert measurement.measurement_rule_version == MEASUREMENT_RULE_VERSION


def test_target_hit_is_success_regardless_of_return_sign(session):
    prediction = _make_prediction(session, "AAA")
    outcome = _make_outcome(session, prediction, outcome="SUCCESS", target_hit=True, actual_return=Decimal("0.05"))

    measurement = measure_outcome(session, outcome, measured_at=MEASURED_AT)

    assert measurement.outcome_classification == OUTCOME_SUCCESS
    assert measurement.realized_return == Decimal("0.05")


def test_stop_hit_is_failure(session):
    prediction = _make_prediction(session, "AAA")
    outcome = _make_outcome(session, prediction, outcome="FAILURE", stop_hit=True, actual_return=Decimal("-0.03"))

    measurement = measure_outcome(session, outcome, measured_at=MEASURED_AT)

    assert measurement.outcome_classification == OUTCOME_FAILURE


def test_near_zero_return_with_no_threshold_hit_is_neutral(session):
    prediction = _make_prediction(session, "AAA")
    outcome = _make_outcome(session, prediction, outcome="SUCCESS", actual_return=Decimal("0"))

    measurement = measure_outcome(session, outcome, measured_at=MEASURED_AT)

    assert measurement.outcome_classification == OUTCOME_NEUTRAL


def test_return_exactly_at_neutral_band_boundary_is_neutral(session):
    prediction = _make_prediction(session, "AAA")
    outcome = _make_outcome(session, prediction, outcome="SUCCESS", actual_return=NEUTRAL_RETURN_BAND)

    measurement = measure_outcome(session, outcome, measured_at=MEASURED_AT)

    assert measurement.outcome_classification == OUTCOME_NEUTRAL


def test_return_just_beyond_neutral_band_is_success_or_failure(session):
    prediction_up = _make_prediction(session, "UP")
    outcome_up = _make_outcome(
        session, prediction_up, outcome="SUCCESS", actual_return=NEUTRAL_RETURN_BAND + Decimal("0.001")
    )
    prediction_down = _make_prediction(session, "DOWN")
    outcome_down = _make_outcome(
        session, prediction_down, outcome="FAILURE", actual_return=-(NEUTRAL_RETURN_BAND + Decimal("0.001"))
    )

    up = measure_outcome(session, outcome_up, measured_at=MEASURED_AT)
    down = measure_outcome(session, outcome_down, measured_at=MEASURED_AT)

    assert up.outcome_classification == OUTCOME_SUCCESS
    assert down.outcome_classification == OUTCOME_FAILURE


def test_measuring_twice_is_idempotent(session):
    prediction = _make_prediction(session, "AAA")
    outcome = _make_outcome(session, prediction, outcome="SUCCESS", target_hit=True, actual_return=Decimal("0.05"))

    first = measure_outcome(session, outcome, measured_at=MEASURED_AT)
    second = measure_outcome(session, outcome, measured_at=MEASURED_AT)

    assert first.id == second.id


def test_measurement_is_immutable_after_creation(session):
    prediction = _make_prediction(session, "AAA")
    outcome = _make_outcome(session, prediction, outcome="SUCCESS", target_hit=True, actual_return=Decimal("0.05"))
    measurement = measure_outcome(session, outcome, measured_at=MEASURED_AT)

    measurement.outcome_classification = OUTCOME_FAILURE
    with pytest.raises(OutcomeMeasurementImmutableError, match="outcome_classification"):
        session.flush()
    session.rollback()


def test_get_outcome_measurement_retrieves_a_prior_measurement(session):
    prediction = _make_prediction(session, "AAA")
    outcome = _make_outcome(session, prediction, outcome="SUCCESS", target_hit=True, actual_return=Decimal("0.05"))
    measure_outcome(session, outcome, measured_at=MEASURED_AT)

    found = get_outcome_measurement(session, outcome.id)

    assert found is not None
    assert found.outcome_classification == OUTCOME_SUCCESS
