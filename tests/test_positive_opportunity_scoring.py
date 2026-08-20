from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.consensus import evaluate_positive_consensus, ConsensusInputs, ConsensusNotQualifiedError
from app.db import Base
from app.models import Stock
from app.scoring import (
    CONTRACT_VERSION,
    LIQUIDITY_CEILING,
    LIQUIDITY_FLOOR,
    PROBABILITY_CEILING,
    PROBABILITY_FLOOR,
    CONFIDENCE_CEILING,
    CONFIDENCE_FLOOR,
    TREND_CEILING,
    InsufficientScoringDataError,
    ScoringInputs,
    compute_positive_opportunity_score,
    rank_positive_opportunities,
    record_ranked_recommendation,
)

STRONG = ScoringInputs(
    predicted_probability=PROBABILITY_CEILING,
    confidence=CONFIDENCE_CEILING,
    sma20_distance=Decimal("0.10"),
    volume_ratio_20d=LIQUIDITY_CEILING,
)

MODERATE = ScoringInputs(
    predicted_probability=Decimal("0.90"),
    confidence=Decimal("0.90"),
    sma20_distance=Decimal("0.10"),
    volume_ratio_20d=Decimal("2.00"),
)

WEAK = ScoringInputs(
    predicted_probability=PROBABILITY_FLOOR,
    confidence=CONFIDENCE_FLOOR,
    sma20_distance=Decimal("0.001"),
    volume_ratio_20d=LIQUIDITY_FLOOR,
)


def _replace(inputs: ScoringInputs, **overrides) -> ScoringInputs:
    return ScoringInputs(**{**inputs.__dict__, **overrides})


def test_maximal_inputs_produce_the_maximum_score():
    result = compute_positive_opportunity_score(STRONG)

    assert result.contract_version == CONTRACT_VERSION
    assert result.total_score == Decimal("100.00")
    assert len(result.components) == 4
    assert all(c.normalized_value == Decimal("1") for c in result.components)


def test_floor_inputs_produce_the_minimum_score():
    result = compute_positive_opportunity_score(WEAK)

    # trend floor here is 0.001, not 0, so it contributes a small nonzero sliver
    assert result.total_score < Decimal("1.00")
    probability_component = next(c for c in result.components if c.name == "probability")
    assert probability_component.normalized_value == Decimal("0")
    assert probability_component.contribution == Decimal("0")


def test_stronger_candidate_scores_higher_than_weaker_one():
    strong_score = compute_positive_opportunity_score(STRONG).total_score
    moderate_score = compute_positive_opportunity_score(MODERATE).total_score
    weak_score = compute_positive_opportunity_score(WEAK).total_score

    assert strong_score > moderate_score > weak_score


@pytest.mark.parametrize(
    "field,floor,ceiling",
    [
        ("predicted_probability", PROBABILITY_FLOOR, PROBABILITY_CEILING),
        ("confidence", CONFIDENCE_FLOOR, CONFIDENCE_CEILING),
        ("volume_ratio_20d", LIQUIDITY_FLOOR, LIQUIDITY_CEILING),
    ],
)
def test_boundary_values_normalize_to_exactly_zero_or_one(field, floor, ceiling):
    at_floor = compute_positive_opportunity_score(_replace(STRONG, **{field: floor}))
    at_ceiling = compute_positive_opportunity_score(_replace(STRONG, **{field: ceiling}))

    component_name = {"predicted_probability": "probability", "confidence": "confidence", "volume_ratio_20d": "liquidity"}[field]
    assert next(c for c in at_floor.components if c.name == component_name).normalized_value == Decimal("0")
    assert next(c for c in at_ceiling.components if c.name == component_name).normalized_value == Decimal("1")


def test_trend_boundary_values():
    at_zero = compute_positive_opportunity_score(_replace(STRONG, sma20_distance=Decimal("0")))
    at_ceiling = compute_positive_opportunity_score(_replace(STRONG, sma20_distance=TREND_CEILING))
    beyond_ceiling = compute_positive_opportunity_score(_replace(STRONG, sma20_distance=TREND_CEILING * 2))

    assert next(c for c in at_zero.components if c.name == "trend").normalized_value == Decimal("0")
    assert next(c for c in at_ceiling.components if c.name == "trend").normalized_value == Decimal("1")
    assert next(c for c in beyond_ceiling.components if c.name == "trend").normalized_value == Decimal("1")


def test_negative_trend_saturates_to_zero_rather_than_erroring():
    result = compute_positive_opportunity_score(_replace(STRONG, sma20_distance=Decimal("-0.05")))
    assert next(c for c in result.components if c.name == "trend").normalized_value == Decimal("0")


@pytest.mark.parametrize(
    "field",
    ["predicted_probability", "confidence", "sma20_distance", "volume_ratio_20d"],
)
def test_missing_data_raises_explicitly(field):
    with pytest.raises(InsufficientScoringDataError, match=field):
        compute_positive_opportunity_score(_replace(STRONG, **{field: None}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("predicted_probability", Decimal("1.01")),
        ("predicted_probability", Decimal("-0.01")),
        ("confidence", Decimal("1.5")),
        ("volume_ratio_20d", Decimal("-1")),
    ],
)
def test_invalid_data_raises_value_error_rather_than_silently_scoring(field, value):
    with pytest.raises(ValueError):
        compute_positive_opportunity_score(_replace(STRONG, **{field: value}))


def test_scoring_is_deterministic_and_repeatable():
    first = compute_positive_opportunity_score(STRONG)
    second = compute_positive_opportunity_score(STRONG)
    assert first == second


def test_ranking_orders_candidates_by_score_descending():
    strong = compute_positive_opportunity_score(STRONG)
    weak = compute_positive_opportunity_score(WEAK)

    ranked = rank_positive_opportunities([("WEAKCO", weak), ("STRONGCO", strong)])

    assert [symbol for symbol, _ in ranked] == ["STRONGCO", "WEAKCO"]


def test_ranking_breaks_exact_ties_by_candidate_key_ascending():
    tied_a = compute_positive_opportunity_score(STRONG)
    tied_b = compute_positive_opportunity_score(STRONG)
    assert tied_a.total_score == tied_b.total_score

    ranked = rank_positive_opportunities([("ZEBRA", tied_b), ("ALPHA", tied_a)])

    assert [symbol for symbol, _ in ranked] == ["ALPHA", "ZEBRA"]


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
        horizon_days=5,
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        model_version="m1-baseline-1",
        feature_version="f1",
    )


def test_qualifying_scored_candidate_is_recorded_with_score_and_version_traced(session):
    stock = _make_stock(session)
    consensus = evaluate_positive_consensus(QUALIFYING_CONSENSUS)
    score = compute_positive_opportunity_score(ScoringInputs(
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
    ))

    rec = record_ranked_recommendation(session, consensus, score, **_recommendation_kwargs(stock.id))

    assert rec.id is not None
    assert rec.scoring_contract_version == CONTRACT_VERSION
    assert rec.opportunity_score == score.total_score


def test_non_qualifying_candidate_cannot_be_scored_and_recorded():
    consensus = evaluate_positive_consensus(
        ConsensusInputs(**{**QUALIFYING_CONSENSUS.__dict__, "data_quality_passed": False})
    )
    score = compute_positive_opportunity_score(ScoringInputs(
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
    ))

    with pytest.raises(ConsensusNotQualifiedError, match="data_quality"):
        record_ranked_recommendation(None, consensus, score, **_recommendation_kwargs(1))
