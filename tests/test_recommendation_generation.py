from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DailyCandidateScan, Prediction, RecommendationGeneration, ScanCandidate, Stock
from app.recommendation_generator import (
    OUTCOME_NOT_QUALIFIED,
    OUTCOME_QUALIFIED,
    CandidateNotEligibleError,
    RecommendationGenerationImmutableError,
    generate_recommendation_for_candidate,
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


def _make_scan(session):
    scan = DailyCandidateScan(scan_date=date(2026, 8, 20), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_stock(session, symbol="RELIANCE"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _make_eligible_candidate(session, scan, stock, **overrides):
    defaults = dict(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
        atr_percent=Decimal("0.035"),
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    defaults.update(overrides)
    candidate = ScanCandidate(**defaults)
    session.add(candidate)
    session.flush()
    return candidate


def _generation_kwargs():
    return dict(
        as_of_timestamp=datetime(2026, 8, 20, tzinfo=timezone.utc),
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )


def test_qualifying_candidate_generates_a_recommendation_and_qualified_record(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    candidate = _make_eligible_candidate(session, scan, stock)

    generation = generate_recommendation_for_candidate(session, candidate, **_generation_kwargs())

    assert generation.outcome == OUTCOME_QUALIFIED
    assert generation.failed_criteria is None
    assert generation.prediction_id is not None

    recommendation = session.get(Prediction, generation.prediction_id)
    assert recommendation is not None
    assert recommendation.stock_id == stock.id
    assert recommendation.opportunity_score > 0
    assert recommendation.horizon_days == 1  # atr_percent=0.035 selects the 1-day horizon


def test_non_qualifying_candidate_records_failed_criteria_without_a_recommendation(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    candidate = _make_eligible_candidate(session, scan, stock, predicted_probability=Decimal("0.40"))

    generation = generate_recommendation_for_candidate(session, candidate, **_generation_kwargs())

    assert generation.outcome == OUTCOME_NOT_QUALIFIED
    assert generation.failed_criteria == ["model_probability"]
    assert generation.prediction_id is None
    assert session.query(Prediction).count() == 0


def test_regenerating_for_the_same_scan_candidate_is_idempotent(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    candidate = _make_eligible_candidate(session, scan, stock)

    first = generate_recommendation_for_candidate(session, candidate, **_generation_kwargs())
    second = generate_recommendation_for_candidate(session, candidate, **_generation_kwargs())

    assert first.id == second.id
    assert session.query(RecommendationGeneration).count() == 1
    assert session.query(Prediction).count() == 1


def test_ineligible_scan_candidate_raises_instead_of_generating(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=False,
        exclusion_reason="missing_market_data",
        data_quality_passed=None,
    )
    session.add(candidate)
    session.flush()

    with pytest.raises(CandidateNotEligibleError, match="missing_market_data"):
        generate_recommendation_for_candidate(session, candidate, **_generation_kwargs())

    assert session.query(RecommendationGeneration).count() == 0


def test_generation_record_is_immutable_after_creation(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    candidate = _make_eligible_candidate(session, scan, stock)
    generation = generate_recommendation_for_candidate(session, candidate, **_generation_kwargs())

    generation.outcome = OUTCOME_NOT_QUALIFIED
    with pytest.raises(RecommendationGenerationImmutableError, match="outcome"):
        session.flush()
    session.rollback()
