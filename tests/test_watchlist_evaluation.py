from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.consensus import ConsensusInputs
from app.db import Base
from app.models import Prediction, Stock
from app.watchlist import (
    BACKLOG_REASON,
    OUTCOME_BACKLOG,
    OUTCOME_PROMOTED,
    WatchlistEvaluationImmutableError,
    evaluate_watchlist_candidate,
    get_watchlist_history,
)

QUALIFYING_INPUTS = ConsensusInputs(
    predicted_probability=Decimal("0.72"),
    confidence=Decimal("0.80"),
    sma20_distance=Decimal("0.03"),
    volume_ratio_20d=Decimal("1.10"),
    data_quality_passed=True,
)

NON_QUALIFYING_INPUTS = ConsensusInputs(
    predicted_probability=Decimal("0.72"),
    confidence=Decimal("0.80"),
    sma20_distance=Decimal("0.03"),
    volume_ratio_20d=Decimal("1.10"),
    data_quality_passed=False,
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


def _make_stock(session, symbol="RELIANCE"):
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, created_at=now, updated_at=now)
    session.add(stock)
    session.flush()
    return stock


def _recommendation_kwargs():
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    return dict(
        as_of_timestamp=now,
        entry_price=Decimal("100"),
        horizon_days=5,
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        model_version="m1-baseline-1",
        feature_version="f1",
    )


def test_qualifying_watchlist_stock_is_promoted_to_a_real_recommendation(session):
    stock = _make_stock(session)
    evaluated_at = datetime(2026, 8, 17, tzinfo=timezone.utc)

    record = evaluate_watchlist_candidate(
        session, stock_id=stock.id, evaluated_at=evaluated_at,
        consensus_inputs=QUALIFYING_INPUTS, recommendation_kwargs=_recommendation_kwargs(),
    )

    assert record.outcome == OUTCOME_PROMOTED
    assert record.qualifies is True
    assert record.failed_criteria == []
    assert record.backlog_reason is None
    assert record.prediction_id is not None

    prediction = session.get(Prediction, record.prediction_id)
    assert prediction is not None
    assert prediction.stock_id == stock.id


def test_non_qualifying_watchlist_stock_enters_backlog_not_a_negative_recommendation(session):
    stock = _make_stock(session)
    evaluated_at = datetime(2026, 8, 17, tzinfo=timezone.utc)

    record = evaluate_watchlist_candidate(
        session, stock_id=stock.id, evaluated_at=evaluated_at,
        consensus_inputs=NON_QUALIFYING_INPUTS, recommendation_kwargs=_recommendation_kwargs(),
    )

    assert record.outcome == OUTCOME_BACKLOG
    assert record.qualifies is False
    assert record.backlog_reason == BACKLOG_REASON
    assert record.prediction_id is None
    # no recommendation was created for the non-qualifying candidate
    assert session.query(Prediction).count() == 0


def test_backlog_record_explains_which_criteria_failed(session):
    stock = _make_stock(session)
    evaluated_at = datetime(2026, 8, 17, tzinfo=timezone.utc)
    inputs = ConsensusInputs(**{**NON_QUALIFYING_INPUTS.__dict__, "predicted_probability": Decimal("0.1")})

    record = evaluate_watchlist_candidate(
        session, stock_id=stock.id, evaluated_at=evaluated_at,
        consensus_inputs=inputs, recommendation_kwargs=_recommendation_kwargs(),
    )

    assert set(record.failed_criteria) == {"model_probability", "data_quality"}


def test_reevaluation_does_not_overwrite_the_prior_evaluation(session):
    stock = _make_stock(session)
    first_at = datetime(2026, 8, 10, tzinfo=timezone.utc)
    second_at = datetime(2026, 8, 17, tzinfo=timezone.utc)

    first = evaluate_watchlist_candidate(
        session, stock_id=stock.id, evaluated_at=first_at,
        consensus_inputs=NON_QUALIFYING_INPUTS, recommendation_kwargs=_recommendation_kwargs(),
    )
    second = evaluate_watchlist_candidate(
        session, stock_id=stock.id, evaluated_at=second_at,
        consensus_inputs=QUALIFYING_INPUTS, recommendation_kwargs=_recommendation_kwargs(),
    )

    assert first.id != second.id
    history = get_watchlist_history(session, stock.id)
    assert [r.id for r in history] == [first.id, second.id]

    # the first evaluation's own record is untouched by the second call
    session.refresh(first)
    assert first.outcome == OUTCOME_BACKLOG
    assert second.outcome == OUTCOME_PROMOTED


def test_watchlist_evaluation_cannot_be_modified_after_creation(session):
    stock = _make_stock(session)
    record = evaluate_watchlist_candidate(
        session, stock_id=stock.id, evaluated_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        consensus_inputs=NON_QUALIFYING_INPUTS, recommendation_kwargs=_recommendation_kwargs(),
    )

    record.outcome = OUTCOME_PROMOTED
    with pytest.raises(WatchlistEvaluationImmutableError, match="outcome"):
        session.flush()
    session.rollback()


def test_watchlist_history_is_ordered_by_evaluation_time(session):
    stock = _make_stock(session)
    later = evaluate_watchlist_candidate(
        session, stock_id=stock.id, evaluated_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        consensus_inputs=NON_QUALIFYING_INPUTS, recommendation_kwargs=_recommendation_kwargs(),
    )
    earlier = evaluate_watchlist_candidate(
        session, stock_id=stock.id, evaluated_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
        consensus_inputs=NON_QUALIFYING_INPUTS, recommendation_kwargs=_recommendation_kwargs(),
    )

    history = get_watchlist_history(session, stock.id)
    assert [r.id for r in history] == [earlier.id, later.id]
