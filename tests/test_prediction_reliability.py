from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.evidence_quality_gate import evaluate_evidence_quality
from app.market_regime import classify_market_regime
from app.models import DailyCandidateScan, Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate, Stock
from app.prediction_reliability import (
    EVIDENCE_STRENGTH_INSUFFICIENT,
    EVIDENCE_STRENGTH_MODERATE,
    EVIDENCE_STRENGTH_STRONG,
    REASON_DATA_QUALITY_INSUFFICIENT,
    REASON_INSUFFICIENT_SAMPLE_SIZE,
    REASON_MARKET_REGIME_UNCERTAIN,
    RELIABILITY_RULE_VERSION,
    assess_prediction_reliability,
    get_reliability_history,
)
from app.regime_transition_intelligence import SOURCE_MARKET, detect_regime_transition, snapshot_prediction_regime_uncertainty

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
_counter = iter(range(1000000))


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


def _make_evaluated_prediction(session, *, outcome, stock=None):
    n = next(_counter)
    scan_date = date(2027, 1, 1) + timedelta(days=n)
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    if stock is None:
        stock = Stock(symbol=f"S{n}", exchange="NSE", is_active=True)
        session.add(stock)
        session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.5"), confidence=Decimal("0.8"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.03"), data_quality_passed=True,
        model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=1,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.5"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.flush()
    session.add(RecommendationGeneration(
        scan_candidate_id=candidate.id, outcome="QUALIFIED", consensus_contract_version="CC-001",
        failed_criteria=None, prediction_id=prediction.id,
    ))
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("110"), lowest_price=Decimal("99"),
        closing_price=Decimal("108"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.01"),
        actual_return=Decimal("0.08"), prediction_error=Decimal("0.01"), target_hit=(outcome == "SUCCESS"),
        stop_hit=(outcome == "FAILURE"), outcome=outcome,
    ))
    session.commit()
    return prediction, stock


def _make_all_success_group(session, count):
    target, stock = _make_evaluated_prediction(session, outcome="SUCCESS")
    for _ in range(count - 1):
        _make_evaluated_prediction(session, outcome="SUCCESS", stock=stock)
    return target


def test_insufficient_below_min_sample_size(session):
    target = _make_all_success_group(session, 10)

    assessment = assess_prediction_reliability(session, target, assessed_at=AS_OF)

    assert assessment.evidence_strength == EVIDENCE_STRENGTH_INSUFFICIENT
    assert assessment.reliable is False
    assert assessment.confidence_interval_lower is None
    assert REASON_INSUFFICIENT_SAMPLE_SIZE in assessment.reasons
    assert assessment.reliability_rule_version == RELIABILITY_RULE_VERSION


def test_small_sample_perfect_record_is_not_strong(session):
    # 30 samples, 100% observed success -- clears MIN_SAMPLE_SIZE but the
    # Wilson interval is still wide enough that this must not be classified
    # the same as a large-sample perfect record (scope: "prevent small-
    # sample high-success histories from producing artificially high Trust").
    target = _make_all_success_group(session, 30)

    assessment = assess_prediction_reliability(session, target, assessed_at=AS_OF)

    assert assessment.observed_rate == Decimal("1")
    assert assessment.confidence_interval_lower is not None
    assert assessment.confidence_interval_lower < Decimal("0.95")
    assert assessment.evidence_strength != EVIDENCE_STRENGTH_STRONG
    assert assessment.evidence_strength == EVIDENCE_STRENGTH_MODERATE


def test_large_sample_perfect_record_is_strong(session):
    target = _make_all_success_group(session, 300)

    assessment = assess_prediction_reliability(session, target, assessed_at=AS_OF)

    assert assessment.observed_rate == Decimal("1")
    assert assessment.evidence_strength == EVIDENCE_STRENGTH_STRONG
    assert assessment.reliable is True


def test_data_uncertain_from_evidence_quality_gate_blocks_reliable(session):
    target = _make_all_success_group(session, 300)
    evaluate_evidence_quality(session, target, evaluated_at=AS_OF)  # no snapshot captured -> STATE_INSUFFICIENT

    assessment = assess_prediction_reliability(session, target, assessed_at=AS_OF)

    assert assessment.evidence_strength == EVIDENCE_STRENGTH_STRONG
    assert assessment.data_uncertain is True
    assert assessment.reliable is False
    assert REASON_DATA_QUALITY_INSUFFICIENT in assessment.reasons


def test_uncertainty_source_none_when_no_regime_snapshot(session):
    target = _make_all_success_group(session, 30)

    assessment = assess_prediction_reliability(session, target, assessed_at=AS_OF)

    assert assessment.uncertainty_source is None
    assert REASON_MARKET_REGIME_UNCERTAIN not in assessment.reasons


def test_uncertainty_source_market_reused_from_regime_transition(session):
    scan_1 = DailyCandidateScan(scan_date=date(2027, 2, 1), universe_version="DCS-002", eligible_count=10, excluded_count=0)
    session.add(scan_1)
    session.flush()
    for i in range(10):
        n = next(_counter)
        stock = Stock(symbol=f"R{n}", exchange="NSE", is_active=True)
        session.add(stock)
        session.flush()
        session.add(ScanCandidate(
            scan_id=scan_1.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
            predicted_probability=Decimal("0.7"), confidence=Decimal("0.8"),
            sma20_distance=Decimal("0.05") if i < 2 else Decimal("-0.05"), volume_ratio_20d=Decimal("1.10"),
            atr_percent=Decimal("0.02"), data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
        ))
    session.commit()
    classify_market_regime(session, scan_1.id)  # 2/10 -> BEARISH

    scan_2 = DailyCandidateScan(scan_date=date(2027, 2, 2), universe_version="DCS-002", eligible_count=10, excluded_count=0)
    session.add(scan_2)
    session.flush()
    for i in range(10):
        n = next(_counter)
        stock = Stock(symbol=f"R{n}", exchange="NSE", is_active=True)
        session.add(stock)
        session.flush()
        session.add(ScanCandidate(
            scan_id=scan_2.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
            predicted_probability=Decimal("0.7"), confidence=Decimal("0.8"),
            sma20_distance=Decimal("0.05") if i < 6 else Decimal("-0.05"), volume_ratio_20d=Decimal("1.10"),
            atr_percent=Decimal("0.02"), data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
        ))
    session.commit()
    classify_market_regime(session, scan_2.id)  # 6/10 -> at boundary, transitioned from BEARISH

    target = _make_all_success_group(session, 30)
    candidate = session.query(ScanCandidate).filter(ScanCandidate.stock_id == target.stock_id).first()
    candidate.scan_id = scan_2.id
    generation = session.query(RecommendationGeneration).filter(RecommendationGeneration.prediction_id == target.id).first()
    generation.scan_candidate_id = candidate.id
    session.commit()

    detect_regime_transition(session, scan_2.id, detected_at=AS_OF, model_version=MODEL_VERSION)
    snapshot_prediction_regime_uncertainty(session, target, snapshotted_at=AS_OF)

    assessment = assess_prediction_reliability(session, target, assessed_at=AS_OF)

    assert assessment.uncertainty_source == SOURCE_MARKET
    assert REASON_MARKET_REGIME_UNCERTAIN in assessment.reasons


def test_idempotent_per_prediction_and_assessed_at(session):
    target = _make_all_success_group(session, 30)

    first = assess_prediction_reliability(session, target, assessed_at=AS_OF)
    second = assess_prediction_reliability(session, target, assessed_at=AS_OF)

    assert first.id == second.id
    assert len(get_reliability_history(session, target.id)) == 1


def test_history_orders_multiple_assessments(session):
    target = _make_all_success_group(session, 30)

    first = assess_prediction_reliability(session, target, assessed_at=AS_OF)
    second = assess_prediction_reliability(session, target, assessed_at=AS_OF + timedelta(days=1))

    history = get_reliability_history(session, target.id)
    assert [h.id for h in history] == [first.id, second.id]
