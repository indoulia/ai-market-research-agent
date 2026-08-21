from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.confidence_quality import QUALITY_HIGH, QUALITY_LOW
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import EVIDENCE_QUALITY_GATE_VERSION, STATE_INSUFFICIENT, STATE_SUFFICIENT
from app.horizon_regime_trust import HORIZON_REGIME_TRUST_VERSION, SEGMENT_COMBINED, VERDICT_SUFFICIENT
from app.model_regression_detection import DETECTION_RULE_VERSION, VERDICT_HEALTHY
from app.models import (
    DailyCandidateScan,
    EvidenceQualityDecision,
    HorizonRegimeTrust,
    MarketPrice,
    ModelRegressionCheck,
    Prediction,
    PredictionCalibrationDrift,
    PredictionTrustScore,
    ScanCandidate,
    Stock,
)
from app.positive_recommendation_gate import (
    POSITIVE_GATE_VERSION,
    REASON_CALIBRATION_DRIFT_DETECTED,
    REASON_EVIDENCE_QUALITY_NOT_SUFFICIENT,
    REASON_SEGMENT_LOW_TRUST,
    REASON_TRUST_QUALITY_TOO_LOW,
    VERDICT_GATE_PASS,
    VERDICT_GATE_SUPPRESSED,
    PositiveRecommendationGateDecisionImmutableError,
    evaluate_positive_gate,
    get_gate_decision_history,
)
from app.prediction_calibration_drift import CALIBRATION_DRIFT_VERSION
from app.prediction_trust_score import PREDICTION_TRUST_SCORE_VERSION

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
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
    scan_date = date(2027, 1, 1) + timedelta(days=next(_scan_counter))
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


def _add_evidence_quality(session, prediction, state):
    session.add(EvidenceQualityDecision(
        prediction_id=prediction.id, state=state, available_category_count=2, stale_category_count=0,
        unavailable_category_count=3, categories_considered=["TECHNICAL_VOLUME", "NEWS"], leaked_categories=[],
        reasons=[], confidence_adjustment_ceiling=prediction.confidence, blocks_publication=(state != STATE_SUFFICIENT),
        evaluated_at=AS_OF, gate_rule_version=EVIDENCE_QUALITY_GATE_VERSION,
    ))
    session.commit()


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
    regression_check = ModelRegressionCheck(
        model_version=MODEL_VERSION, baseline_window_label="baseline", baseline_success_rate=Decimal("1"),
        baseline_sample_count=20, monitoring_window_label="monitoring", monitoring_success_rate=Decimal("1"),
        monitoring_sample_count=20, verdict=VERDICT_HEALTHY, segment_regressions=[], rollback_triggered=False,
        checked_at=AS_OF, detection_rule_version=DETECTION_RULE_VERSION,
    )
    session.add(regression_check)
    session.flush()
    session.add(PredictionCalibrationDrift(
        model_version=MODEL_VERSION, baseline_window_label="baseline", baseline_sample_count=20,
        monitoring_window_label="monitoring", monitoring_sample_count=20,
        baseline_mean_predicted_probability=Decimal("0.7"), monitoring_mean_predicted_probability=Decimal("0.7"),
        distribution_drift=Decimal("0"), distribution_drift_detected=False, baseline_calibration_error=Decimal("0"),
        monitoring_calibration_error=Decimal("0"), calibration_drift=Decimal("0"), calibration_drift_detected=False,
        model_regression_check_id=regression_check.id,
        verdict="DRIFT_DETECTED" if trust_reduction_recommended else "NO_DRIFT",
        trust_reduction_recommended=trust_reduction_recommended, checked_at=AS_OF,
        drift_rule_version=CALIBRATION_DRIFT_VERSION,
    ))
    session.commit()


def test_no_signals_computed_is_suppressed(session):
    prediction = _make_prediction(session)

    decision = evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)

    assert decision.verdict == VERDICT_GATE_SUPPRESSED
    assert decision.evidence_quality_met is False
    assert decision.trust_quality_met is False
    assert decision.segment_trust_met is True  # optional, not yet computed
    assert decision.calibration_drift_met is True  # optional, not yet computed
    assert set(decision.suppression_reasons) == {REASON_EVIDENCE_QUALITY_NOT_SUFFICIENT, REASON_TRUST_QUALITY_TOO_LOW}
    assert decision.gate_rule_version == POSITIVE_GATE_VERSION


def test_all_signals_passing_is_gate_pass(session):
    prediction = _make_prediction(session)
    _add_evidence_quality(session, prediction, STATE_SUFFICIENT)
    _add_trust_score(session, prediction, QUALITY_HIGH)
    _add_segment_trust(session, regime="BULLISH_HIGH_VOL", is_low_trust=False)
    _add_calibration_drift(session, trust_reduction_recommended=False)

    decision = evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)

    assert decision.verdict == VERDICT_GATE_PASS
    assert decision.suppression_reasons == []
    assert all([decision.evidence_quality_met, decision.trust_quality_met, decision.segment_trust_met, decision.calibration_drift_met])


def test_low_trust_quality_alone_suppresses(session):
    prediction = _make_prediction(session)
    _add_evidence_quality(session, prediction, STATE_SUFFICIENT)
    _add_trust_score(session, prediction, QUALITY_LOW)

    decision = evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)

    assert decision.verdict == VERDICT_GATE_SUPPRESSED
    assert decision.suppression_reasons == [REASON_TRUST_QUALITY_TOO_LOW]


def test_segment_low_trust_suppresses_when_computed(session):
    prediction = _make_prediction(session)
    _add_evidence_quality(session, prediction, STATE_SUFFICIENT)
    _add_trust_score(session, prediction, QUALITY_HIGH)
    _add_segment_trust(session, regime="BULLISH_HIGH_VOL", is_low_trust=True)

    decision = evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)

    assert decision.verdict == VERDICT_GATE_SUPPRESSED
    assert decision.suppression_reasons == [REASON_SEGMENT_LOW_TRUST]


def test_calibration_drift_suppresses_when_computed(session):
    prediction = _make_prediction(session)
    _add_evidence_quality(session, prediction, STATE_SUFFICIENT)
    _add_trust_score(session, prediction, QUALITY_HIGH)
    _add_calibration_drift(session, trust_reduction_recommended=True)

    decision = evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)

    assert decision.verdict == VERDICT_GATE_SUPPRESSED
    assert decision.suppression_reasons == [REASON_CALIBRATION_DRIFT_DETECTED]


def test_insufficient_evidence_quality_suppresses(session):
    prediction = _make_prediction(session)
    _add_evidence_quality(session, prediction, STATE_INSUFFICIENT)
    _add_trust_score(session, prediction, QUALITY_HIGH)

    decision = evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)

    assert decision.verdict == VERDICT_GATE_SUPPRESSED
    assert decision.suppression_reasons == [REASON_EVIDENCE_QUALITY_NOT_SUFFICIENT]


def test_idempotent_and_history(session):
    prediction = _make_prediction(session)

    first = evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)
    second = evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)
    third = evaluate_positive_gate(session, prediction, evaluated_at=AS_OF + timedelta(hours=1))

    assert first.id == second.id
    assert third.id != first.id
    assert len(get_gate_decision_history(session, prediction.id)) == 2


def test_decision_is_immutable(session):
    prediction = _make_prediction(session)
    decision = evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)

    decision.verdict = VERDICT_GATE_PASS
    with pytest.raises(PositiveRecommendationGateDecisionImmutableError):
        session.commit()
    session.rollback()


def test_never_writes_to_prediction_or_dependencies(session):
    prediction = _make_prediction(session)
    _add_evidence_quality(session, prediction, STATE_SUFFICIENT)
    _add_trust_score(session, prediction, QUALITY_HIGH)
    before_prediction = (prediction.confidence, prediction.opportunity_score)
    before_eq_count = session.query(EvidenceQualityDecision).count()
    before_ts_count = session.query(PredictionTrustScore).count()

    evaluate_positive_gate(session, prediction, evaluated_at=AS_OF)

    after_prediction = (prediction.confidence, prediction.opportunity_score)
    after_eq_count = session.query(EvidenceQualityDecision).count()
    after_ts_count = session.query(PredictionTrustScore).count()
    assert before_prediction == after_prediction
    assert before_eq_count == after_eq_count
    assert before_ts_count == after_ts_count
