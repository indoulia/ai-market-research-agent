from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.consensus import (
    CONTRACT_VERSION,
    MIN_CONFIDENCE,
    MIN_PREDICTED_PROBABILITY,
    MIN_VOLUME_RATIO_20D,
    ConsensusInputs,
    ConsensusNotQualifiedError,
    evaluate_positive_consensus,
    record_qualifying_recommendation,
)
from app.db import Base
from app.models import Stock

QUALIFYING = ConsensusInputs(
    predicted_probability=Decimal("0.72"),
    confidence=Decimal("0.80"),
    sma20_distance=Decimal("0.03"),
    volume_ratio_20d=Decimal("1.10"),
    data_quality_passed=True,
)


def _replace(inputs: ConsensusInputs, **overrides) -> ConsensusInputs:
    return ConsensusInputs(**{**inputs.__dict__, **overrides})


def test_qualifying_candidate_passes_every_criterion():
    evaluation = evaluate_positive_consensus(QUALIFYING)

    assert evaluation.qualifies is True
    assert evaluation.contract_version == CONTRACT_VERSION
    assert len(evaluation.criteria) == 5
    assert all(c.passed for c in evaluation.criteria)
    assert evaluation.failed_criteria() == ()


@pytest.mark.parametrize("value", [MIN_PREDICTED_PROBABILITY, MIN_CONFIDENCE, MIN_VOLUME_RATIO_20D])
def test_threshold_boundary_is_inclusive(value):
    # exactly-at-threshold cases across all three numeric thresholds must PASS ("borderline" AC)
    borderline = _replace(
        QUALIFYING,
        predicted_probability=MIN_PREDICTED_PROBABILITY,
        confidence=MIN_CONFIDENCE,
        volume_ratio_20d=MIN_VOLUME_RATIO_20D,
    )
    evaluation = evaluate_positive_consensus(borderline)
    assert evaluation.qualifies is True


@pytest.mark.parametrize(
    "field,value,expected_failed",
    [
        ("predicted_probability", MIN_PREDICTED_PROBABILITY - Decimal("0.01"), "model_probability"),
        ("confidence", MIN_CONFIDENCE - Decimal("0.01"), "model_confidence"),
        ("sma20_distance", Decimal("0"), "positive_trend"),
        ("sma20_distance", Decimal("-0.01"), "positive_trend"),
        ("volume_ratio_20d", MIN_VOLUME_RATIO_20D - Decimal("0.01"), "sufficient_liquidity"),
        ("data_quality_passed", False, "data_quality"),
    ],
)
def test_failing_candidate_reports_the_specific_failed_criterion(field, value, expected_failed):
    evaluation = evaluate_positive_consensus(_replace(QUALIFYING, **{field: value}))

    assert evaluation.qualifies is False
    failed_names = [c.name for c in evaluation.failed_criteria()]
    assert failed_names == [expected_failed]
    # every other criterion still independently passed
    assert len(evaluation.criteria) == 5


@pytest.mark.parametrize(
    "field,expected_failed",
    [
        ("predicted_probability", "model_probability"),
        ("confidence", "model_confidence"),
        ("sma20_distance", "positive_trend"),
        ("volume_ratio_20d", "sufficient_liquidity"),
        ("data_quality_passed", "data_quality"),
    ],
)
def test_missing_data_fails_explicitly_rather_than_defaulting(field, expected_failed):
    evaluation = evaluate_positive_consensus(_replace(QUALIFYING, **{field: None}))

    assert evaluation.qualifies is False
    failed = evaluation.failed_criteria()
    assert len(failed) == 1
    assert failed[0].name == expected_failed
    assert "missing" in failed[0].detail


def test_multiple_failures_are_all_reported_independently():
    inputs = _replace(QUALIFYING, predicted_probability=Decimal("0.1"), data_quality_passed=False)
    evaluation = evaluate_positive_consensus(inputs)

    assert evaluation.qualifies is False
    failed_names = {c.name for c in evaluation.failed_criteria()}
    assert failed_names == {"model_probability", "data_quality"}


def test_evaluation_is_deterministic_and_repeatable():
    first = evaluate_positive_consensus(QUALIFYING)
    second = evaluate_positive_consensus(QUALIFYING)
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


def _recommendation_kwargs(stock_id):
    now = datetime(2026, 8, 17, tzinfo=timezone.utc)
    return dict(
        stock_id=stock_id,
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


def _make_stock(session):
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    stock = Stock(symbol="RELIANCE", exchange="NSE", is_active=True, created_at=now, updated_at=now)
    session.add(stock)
    session.flush()
    return stock


def test_qualifying_candidate_can_be_recorded_with_contract_version_traced(session):
    stock = _make_stock(session)
    evaluation = evaluate_positive_consensus(QUALIFYING)

    rec = record_qualifying_recommendation(session, evaluation, **_recommendation_kwargs(stock.id))

    assert rec.id is not None
    assert rec.consensus_contract_version == CONTRACT_VERSION


def test_non_qualifying_candidate_cannot_be_recorded():
    evaluation = evaluate_positive_consensus(_replace(QUALIFYING, data_quality_passed=False))

    with pytest.raises(ConsensusNotQualifiedError, match="data_quality"):
        record_qualifying_recommendation(None, evaluation, **_recommendation_kwargs(1))
