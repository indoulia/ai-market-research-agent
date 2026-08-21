from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.execution_cost_model import (
    BASE_SPREAD_COST_BPS,
    BASE_TRANSACTION_COST_BPS,
    EXECUTABILITY_EXECUTABLE,
    EXECUTABILITY_ILLIQUID,
    EXECUTABILITY_UNAVAILABLE,
    EXECUTION_COST_MODEL_VERSION,
    ExecutionCostAssessmentImmutableError,
    LOW_LIQUIDITY_SLIPPAGE_SURCHARGE_BPS,
    assess_execution_cost,
    compute_cost_sensitivity,
    get_execution_cost_assessment,
)
from app.models import DailyCandidateScan, MarketPrice, Prediction, RecommendationGeneration, ScanCandidate, Stock
from app.outcomes import evaluate_recommendation
from app.recommendations import record_recommendation

AS_OF = datetime(2027, 6, 1, tzinfo=timezone.utc)
_scan_counter = iter(range(100000))


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


def make_prediction_via_real_pipeline(session, symbol="AAA", *, volume_ratio_20d=Decimal("1.10")):
    scan_date = AS_OF.date() + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=volume_ratio_20d, atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    return prediction, stock


def add_price(session, stock_id, close, *, at, valid=True):
    close = Decimal(str(close))
    session.add(MarketPrice(
        stock_id=stock_id, timestamp=at,
        open=close if valid else Decimal("0"), high=close + Decimal("1") if valid else Decimal("-5"),
        low=close - Decimal("1") if valid else Decimal("999"), close=close,
        volume=1000 if valid else 0, source="test",
    ))
    session.flush()


def test_executable_case_computes_net_return_below_gross(session):
    prediction, stock = make_prediction_via_real_pipeline(session, volume_ratio_20d=Decimal("1.10"))
    add_price(session, stock.id, "101", at=AS_OF + timedelta(days=1))
    outcome = evaluate_recommendation(session, prediction)

    assessment = assess_execution_cost(session, prediction, outcome, assessed_at=AS_OF)

    assert assessment.executability_verdict == EXECUTABILITY_EXECUTABLE
    assert assessment.liquidity_bucket in ("HIGH", "NORMAL")
    assert assessment.gross_return == outcome.actual_return
    expected_cost = (BASE_SPREAD_COST_BPS + BASE_TRANSACTION_COST_BPS) / Decimal("10000")
    assert assessment.estimated_cost_percent == expected_cost
    assert assessment.net_return == outcome.actual_return - expected_cost
    assert assessment.net_return < assessment.gross_return
    assert assessment.cost_model_version == EXECUTION_COST_MODEL_VERSION


def test_low_liquidity_case_applies_a_surcharge(session):
    """A real, platform-produced `Prediction` can never carry a `LOW`
    liquidity bucket -- M1.8's own consensus gate already requires
    `volume_ratio_20d >= 0.75` (M1.8's `MIN_VOLUME_RATIO_20D`), which is
    exactly the `NORMAL`/`HIGH` boundary. This exercises the `ILLIQUID`
    path directly, the same way this session has repeatedly tested other
    honestly-unreachable-by-live-data vocabulary (M1.75's day-2 horizon,
    M1.79's bearish regime segment) -- by constructing the scenario
    directly rather than fabricating a way around the gate."""
    scan_date = AS_OF.date() + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol="LOWLIQ", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("0.50"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    prediction = record_recommendation(
        session, stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=1,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"), model_version="test-model-1", feature_version="FV-001",
        consensus_contract_version="PCC-001", horizon_selection_version="PHS-001",
        scoring_contract_version="POS-001", opportunity_score=Decimal("70.00"),
    )
    session.add(RecommendationGeneration(
        scan_candidate_id=candidate.id, outcome="QUALIFIED", consensus_contract_version="PCC-001",
        failed_criteria=None, prediction_id=prediction.id,
    ))
    session.commit()
    add_price(session, stock.id, "101", at=AS_OF + timedelta(days=1))
    outcome = evaluate_recommendation(session, prediction)

    assessment = assess_execution_cost(session, prediction, outcome, assessed_at=AS_OF)

    assert assessment.liquidity_bucket == "LOW"
    assert assessment.executability_verdict == EXECUTABILITY_ILLIQUID
    expected_cost = (BASE_SPREAD_COST_BPS + BASE_TRANSACTION_COST_BPS + LOW_LIQUIDITY_SLIPPAGE_SURCHARGE_BPS) / Decimal("10000")
    assert assessment.estimated_cost_percent == expected_cost
    assert assessment.net_return == outcome.actual_return - expected_cost


def test_unevaluable_outcome_has_no_net_return(session):
    prediction, stock = make_prediction_via_real_pipeline(session)
    add_price(session, stock.id, "101", at=AS_OF + timedelta(days=1), valid=False)
    outcome = evaluate_recommendation(session, prediction)
    assert outcome.outcome == "UNEVALUABLE"

    assessment = assess_execution_cost(session, prediction, outcome, assessed_at=AS_OF)

    assert assessment.executability_verdict == EXECUTABILITY_UNAVAILABLE
    assert assessment.estimated_cost_percent is None
    assert assessment.net_return is None
    assert assessment.gross_return == outcome.actual_return  # gross preserved even when net is unavailable


def test_missing_scan_candidate_link_is_unavailable(session):
    stock = Stock(symbol="ZZZ", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    prediction = record_recommendation(
        session, stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=1,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version="m1", feature_version="f1",
        consensus_contract_version="PCC-001", horizon_selection_version="PHS-001",
        scoring_contract_version="POS-001", opportunity_score=Decimal("70.00"),
    )
    add_price(session, stock.id, "101", at=AS_OF + timedelta(days=1))
    outcome = evaluate_recommendation(session, prediction)

    assessment = assess_execution_cost(session, prediction, outcome, assessed_at=AS_OF)

    assert assessment.executability_verdict == EXECUTABILITY_UNAVAILABLE
    assert assessment.net_return is None


def test_assessment_is_idempotent(session):
    prediction, stock = make_prediction_via_real_pipeline(session)
    add_price(session, stock.id, "101", at=AS_OF + timedelta(days=1))
    outcome = evaluate_recommendation(session, prediction)

    first = assess_execution_cost(session, prediction, outcome, assessed_at=AS_OF)
    second = assess_execution_cost(session, prediction, outcome, assessed_at=AS_OF)

    assert first.id == second.id


def test_assessment_fields_are_immutable(session):
    prediction, stock = make_prediction_via_real_pipeline(session)
    add_price(session, stock.id, "101", at=AS_OF + timedelta(days=1))
    outcome = evaluate_recommendation(session, prediction)
    assessment = assess_execution_cost(session, prediction, outcome, assessed_at=AS_OF)

    assessment.net_return = Decimal("0.99")
    with pytest.raises(ExecutionCostAssessmentImmutableError):
        session.flush()
    session.rollback()


def test_get_execution_cost_assessment_returns_none_when_absent(session):
    prediction, _ = make_prediction_via_real_pipeline(session)
    assert get_execution_cost_assessment(session, prediction.id) is None


def test_sensitivity_scales_the_assumed_cost(session):
    prediction, stock = make_prediction_via_real_pipeline(session)
    add_price(session, stock.id, "101", at=AS_OF + timedelta(days=1))
    outcome = evaluate_recommendation(session, prediction)
    assessment = assess_execution_cost(session, prediction, outcome, assessed_at=AS_OF)

    points = compute_cost_sensitivity(assessment, multipliers=(Decimal("0.5"), Decimal("1"), Decimal("2")))

    assert len(points) == 3
    base_cost = assessment.estimated_cost_percent
    for point in points:
        expected = assessment.gross_return - (base_cost * point.cost_multiplier)
        assert point.net_return == expected
    # a higher multiplier must never produce a higher net return
    assert points[2].net_return < points[1].net_return < points[0].net_return


def test_sensitivity_is_empty_when_cost_is_unavailable(session):
    prediction, stock = make_prediction_via_real_pipeline(session)
    add_price(session, stock.id, "101", at=AS_OF + timedelta(days=1), valid=False)
    outcome = evaluate_recommendation(session, prediction)
    assessment = assess_execution_cost(session, prediction, outcome, assessed_at=AS_OF)

    assert compute_cost_sensitivity(assessment) == ()


def test_reproducible_given_the_same_inputs(session):
    prediction, stock = make_prediction_via_real_pipeline(session)
    add_price(session, stock.id, "101", at=AS_OF + timedelta(days=1))
    outcome = evaluate_recommendation(session, prediction)

    first = assess_execution_cost(session, prediction, outcome, assessed_at=AS_OF).net_return
    reread = get_execution_cost_assessment(session, prediction.id).net_return

    assert first == reread
