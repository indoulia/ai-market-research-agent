from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.consensus import ConsensusInputs, evaluate_positive_consensus
from app.db import Base
from app.horizon import (
    ATR_PERCENT_HORIZON_THRESHOLDS,
    FALLBACK_HORIZON_DAYS,
    SELECTION_VERSION,
    InsufficientHorizonEvidenceError,
    record_recommendation_with_selected_horizon,
    select_horizon,
)
from app.models import Stock
from app.recommendations import VALID_HORIZON_DAYS


def test_every_configured_output_is_a_supported_horizon():
    assert FALLBACK_HORIZON_DAYS in VALID_HORIZON_DAYS
    assert all(h in VALID_HORIZON_DAYS for _, h in ATR_PERCENT_HORIZON_THRESHOLDS)


@pytest.mark.parametrize(
    "atr_percent,expected_horizon",
    [
        (Decimal("0.05"), 1),
        (Decimal("0.035"), 1),   # exact boundary: inclusive
        (Decimal("0.034"), 3),
        (Decimal("0.020"), 3),   # exact boundary: inclusive
        (Decimal("0.019"), 5),
        (Decimal("0.010"), 5),   # exact boundary: inclusive
        (Decimal("0.009"), 7),
        (Decimal("0"), 7),
    ],
)
def test_selects_each_supported_horizon_from_atr_percent(atr_percent, expected_horizon):
    selection = select_horizon(atr_percent)

    assert selection.horizon_days == expected_horizon
    assert selection.horizon_days in VALID_HORIZON_DAYS
    assert selection.selection_version == SELECTION_VERSION


def test_fallback_horizon_is_used_below_every_threshold():
    selection = select_horizon(Decimal("0.001"))
    assert selection.horizon_days == FALLBACK_HORIZON_DAYS


def test_missing_evidence_raises_explicitly_rather_than_defaulting():
    with pytest.raises(InsufficientHorizonEvidenceError, match="atr_percent"):
        select_horizon(None)


def test_negative_atr_percent_raises_value_error():
    with pytest.raises(ValueError, match="atr_percent"):
        select_horizon(Decimal("-0.01"))


def test_selection_is_deterministic_and_repeatable():
    first = select_horizon(Decimal("0.025"))
    second = select_horizon(Decimal("0.025"))
    assert first == second


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


def _make_stock(session):
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    stock = Stock(symbol="RELIANCE", exchange="NSE", is_active=True, created_at=now, updated_at=now)
    session.add(stock)
    session.flush()
    return stock


QUALIFYING_CONSENSUS = ConsensusInputs(
    predicted_probability=Decimal("0.72"),
    confidence=Decimal("0.80"),
    sma20_distance=Decimal("0.03"),
    volume_ratio_20d=Decimal("1.10"),
    data_quality_passed=True,
)


def _recommendation_kwargs(stock_id):
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    return dict(
        stock_id=stock_id,
        as_of_timestamp=now,
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        model_version="m1-baseline-1",
        feature_version="f1",
    )


def test_qualifying_candidate_is_recorded_with_selected_horizon_and_version_traced(session):
    stock = _make_stock(session)
    consensus = evaluate_positive_consensus(QUALIFYING_CONSENSUS)

    rec = record_recommendation_with_selected_horizon(
        session, consensus, Decimal("0.035"), **_recommendation_kwargs(stock.id)
    )

    assert rec.id is not None
    assert rec.horizon_days == 1
    assert rec.horizon_selection_version == SELECTION_VERSION


def test_missing_evidence_prevents_recommendation_from_being_recorded(session):
    stock = _make_stock(session)
    consensus = evaluate_positive_consensus(QUALIFYING_CONSENSUS)

    with pytest.raises(InsufficientHorizonEvidenceError):
        record_recommendation_with_selected_horizon(session, consensus, None, **_recommendation_kwargs(stock.id))

    # nothing was persisted
    from app.models import Prediction
    assert session.query(Prediction).count() == 0


def test_horizon_selection_version_cannot_be_modified_after_creation(session):
    stock = _make_stock(session)
    consensus = evaluate_positive_consensus(QUALIFYING_CONSENSUS)
    rec = record_recommendation_with_selected_horizon(
        session, consensus, Decimal("0.035"), **_recommendation_kwargs(stock.id)
    )

    from app.recommendations import RecommendationImmutableError

    rec.horizon_selection_version = "PHS-999"
    with pytest.raises(RecommendationImmutableError, match="horizon_selection_version"):
        session.flush()
    session.rollback()


def test_horizon_days_cannot_be_modified_after_creation(session):
    stock = _make_stock(session)
    consensus = evaluate_positive_consensus(QUALIFYING_CONSENSUS)
    rec = record_recommendation_with_selected_horizon(
        session, consensus, Decimal("0.035"), **_recommendation_kwargs(stock.id)
    )

    from app.recommendations import RecommendationImmutableError

    rec.horizon_days = 7
    with pytest.raises(RecommendationImmutableError, match="horizon_days"):
        session.flush()
    session.rollback()
