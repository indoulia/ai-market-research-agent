from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.confidence_quality import QUALITY_HIGH, QUALITY_INSUFFICIENT_DATA
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.horizon_regime_trust import HORIZON_REGIME_TRUST_VERSION, SEGMENT_COMBINED, VERDICT_SUFFICIENT
from app.models import (
    DailyCandidateScan,
    HorizonRegimeTrust,
    MarketPrice,
    Prediction,
    PredictionCalibrationDrift,
    PredictionQualityBenchmarkReport,
    PredictionStabilityAssessment,
    PredictionTrustScore,
    ScanCandidate,
    Stock,
)
from app.prediction_calibration_drift import CALIBRATION_DRIFT_VERSION
from app.prediction_quality_benchmark import BENCHMARK_NOT_REQUESTED, QUALITY_BENCHMARK_VERSION, VERDICT_MEASURED
from app.prediction_stability import (
    AGREEMENT_VERDICT_NO_DATA,
    STABILITY_ASSESSMENT_VERSION,
    STABILITY_VERDICT_STABLE,
)
from app.prediction_trust_score import PREDICTION_TRUST_SCORE_VERSION
from app.trust_control import (
    ACTION_NONE,
    ACTION_TRIGGER_MODEL_COMPARISON,
    ACTION_TRIGGER_RECALIBRATION,
    ACTION_TRIGGER_REVALIDATION,
    CAUSE_BENCHMARK_UNDERPERFORMANCE,
    CAUSE_CALIBRATION_DRIFT,
    CAUSE_INSTABILITY,
    CAUSE_LOW_TRUST_QUALITY,
    CAUSE_SEGMENT_LOW_TRUST,
    TRUST_CONTROL_VERSION,
    TrustControlDecisionImmutableError,
    evaluate_trust_control,
    get_control_decision_history,
)

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 3, 1, tzinfo=timezone.utc)
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


def _make_prediction(session, symbol="AAA"):
    scan_date = date(2027, 3, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=1000, source="test",
    ))
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    assert prediction.horizon_days == 1
    return prediction


def _add_trust_score(session, prediction, quality):
    session.add(PredictionTrustScore(
        prediction_id=prediction.id, overall_trust_score=Decimal("0.9") if quality == QUALITY_HIGH else Decimal("0.2"),
        trust_quality=quality, calibration_component=None, historical_accuracy_component=None,
        recent_performance_component=None, horizon_reliability_component=None, regime_reliability_component=None,
        evidence_quality_component=None, available_component_count=1, reasons=[], computed_at=AS_OF,
        trust_score_version=PREDICTION_TRUST_SCORE_VERSION,
    ))
    session.commit()


def _add_segment_trust(session, *, regime, is_low_trust):
    session.add(HorizonRegimeTrust(
        model_version=MODEL_VERSION, segment_type=SEGMENT_COMBINED, horizon_days=1, regime=regime,
        sample_count=20, success_rate=Decimal("0.2") if is_low_trust else Decimal("0.8"),
        success_rate_standard_error=Decimal("0.05"), verdict=VERDICT_SUFFICIENT, is_low_trust=is_low_trust,
        computed_at=AS_OF, trust_rule_version=HORIZON_REGIME_TRUST_VERSION,
    ))
    session.commit()


def _add_calibration_drift(session, *, trust_reduction_recommended):
    session.add(PredictionCalibrationDrift(
        model_version=MODEL_VERSION, baseline_window_label="baseline", baseline_sample_count=20,
        monitoring_window_label="monitoring", monitoring_sample_count=20,
        baseline_mean_predicted_probability=Decimal("0.7"), monitoring_mean_predicted_probability=Decimal("0.7"),
        distribution_drift=Decimal("0"), distribution_drift_detected=False, baseline_calibration_error=Decimal("0"),
        monitoring_calibration_error=Decimal("0"), calibration_drift=Decimal("0"), calibration_drift_detected=False,
        model_regression_check_id=None, verdict="DRIFT_DETECTED" if trust_reduction_recommended else "NO_DRIFT",
        trust_reduction_recommended=trust_reduction_recommended, checked_at=AS_OF,
        drift_rule_version=CALIBRATION_DRIFT_VERSION,
    ))
    session.commit()


def _add_benchmark_report(session, *, trust_reduction_recommended):
    session.add(PredictionQualityBenchmarkReport(
        model_version=MODEL_VERSION, window_label="full-history", sample_count=20, directional_accuracy=Decimal("0.7"),
        target_hit_rate=Decimal("0.7"), stop_hit_rate=Decimal("0.3"), avg_expected_return=Decimal("0.05"),
        avg_realized_return=Decimal("0.03"), avg_max_favorable_excursion=Decimal("0.05"),
        avg_max_adverse_excursion=Decimal("-0.02"), avg_time_to_exit_days=Decimal("1"), benchmark_stock_id=None,
        avg_benchmark_return=None, avg_excess_return=None, benchmark_coverage_count=0,
        benchmark_verdict=BENCHMARK_NOT_REQUESTED, segment_breakdown=[], verdict=VERDICT_MEASURED,
        trust_reduction_recommended=trust_reduction_recommended, computed_at=AS_OF,
        benchmark_rule_version=QUALITY_BENCHMARK_VERSION,
    ))
    session.commit()


def _add_stability_assessment(session, prediction, *, trust_reduction_recommended):
    session.add(PredictionStabilityAssessment(
        original_prediction_id=prediction.id, revision_count=0, max_score_delta=None, max_confidence_delta=None,
        unexplained_revision_count=0, stability_verdict=STABILITY_VERDICT_STABLE,
        model_agreement_verdict=AGREEMENT_VERDICT_NO_DATA, model_agreement_score_delta=None,
        stability_backed_by_outcomes=False, trust_reduction_recommended=trust_reduction_recommended,
        assessed_at=AS_OF, assessment_rule_version=STABILITY_ASSESSMENT_VERSION,
    ))
    session.commit()


def test_no_signals_reduces_eligibility_on_missing_trust_score(session):
    prediction = _make_prediction(session)

    decision = evaluate_trust_control(session, prediction, evaluated_at=AS_OF)

    assert decision.overall_trust_quality == QUALITY_INSUFFICIENT_DATA
    assert decision.eligibility_reduced is True
    assert decision.causes == [CAUSE_LOW_TRUST_QUALITY]
    assert decision.recommended_action == ACTION_TRIGGER_RECALIBRATION
    assert decision.control_rule_version == TRUST_CONTROL_VERSION


def test_high_trust_and_all_signals_ok_is_no_reduction(session):
    prediction = _make_prediction(session)
    _add_trust_score(session, prediction, QUALITY_HIGH)

    decision = evaluate_trust_control(session, prediction, evaluated_at=AS_OF)

    assert decision.eligibility_reduced is False
    assert decision.causes == []
    assert decision.recommended_action == ACTION_NONE
    assert all([decision.segment_trust_ok, decision.calibration_drift_ok, decision.benchmark_performance_ok, decision.stability_ok])


def test_calibration_drift_triggers_model_comparison(session):
    prediction = _make_prediction(session)
    _add_trust_score(session, prediction, QUALITY_HIGH)
    _add_calibration_drift(session, trust_reduction_recommended=True)

    decision = evaluate_trust_control(session, prediction, evaluated_at=AS_OF)

    assert decision.causes == [CAUSE_CALIBRATION_DRIFT]
    assert decision.recommended_action == ACTION_TRIGGER_MODEL_COMPARISON


def test_benchmark_underperformance_triggers_model_comparison(session):
    prediction = _make_prediction(session)
    _add_trust_score(session, prediction, QUALITY_HIGH)
    _add_benchmark_report(session, trust_reduction_recommended=True)

    decision = evaluate_trust_control(session, prediction, evaluated_at=AS_OF)

    assert decision.causes == [CAUSE_BENCHMARK_UNDERPERFORMANCE]
    assert decision.recommended_action == ACTION_TRIGGER_MODEL_COMPARISON


def test_instability_triggers_revalidation(session):
    prediction = _make_prediction(session)
    _add_trust_score(session, prediction, QUALITY_HIGH)
    _add_stability_assessment(session, prediction, trust_reduction_recommended=True)

    decision = evaluate_trust_control(session, prediction, evaluated_at=AS_OF)

    assert decision.causes == [CAUSE_INSTABILITY]
    assert decision.recommended_action == ACTION_TRIGGER_REVALIDATION


def test_segment_low_trust_reduces_eligibility_with_recalibration_action(session):
    prediction = _make_prediction(session)
    _add_trust_score(session, prediction, QUALITY_HIGH)
    _add_segment_trust(session, regime="BULLISH_HIGH_VOL", is_low_trust=True)

    decision = evaluate_trust_control(session, prediction, evaluated_at=AS_OF)

    assert decision.causes == [CAUSE_SEGMENT_LOW_TRUST]
    assert decision.eligibility_reduced is True
    assert decision.recommended_action == ACTION_TRIGGER_RECALIBRATION


def test_idempotent_and_history(session):
    prediction = _make_prediction(session)

    first = evaluate_trust_control(session, prediction, evaluated_at=AS_OF)
    second = evaluate_trust_control(session, prediction, evaluated_at=AS_OF)
    third = evaluate_trust_control(session, prediction, evaluated_at=AS_OF + timedelta(hours=1))

    assert first.id == second.id
    assert third.id != first.id
    assert len(get_control_decision_history(session, prediction.id)) == 2


def test_decision_is_immutable(session):
    prediction = _make_prediction(session)
    decision = evaluate_trust_control(session, prediction, evaluated_at=AS_OF)

    decision.eligibility_reduced = False
    with pytest.raises(TrustControlDecisionImmutableError):
        session.commit()
    session.rollback()


def test_never_writes_to_prediction_or_dependencies(session):
    prediction = _make_prediction(session)
    _add_trust_score(session, prediction, QUALITY_HIGH)
    before_prediction = (prediction.confidence, prediction.opportunity_score)
    before_ts_count = session.query(PredictionTrustScore).count()

    evaluate_trust_control(session, prediction, evaluated_at=AS_OF)

    after_prediction = (prediction.confidence, prediction.opportunity_score)
    after_ts_count = session.query(PredictionTrustScore).count()
    assert before_prediction == after_prediction
    assert before_ts_count == after_ts_count
