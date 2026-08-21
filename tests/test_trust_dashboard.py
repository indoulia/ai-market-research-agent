from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.evidence_quality_gate import STATE_INSUFFICIENT, STATE_SUFFICIENT
from app.horizon_regime_trust import SEGMENT_COMBINED
from app.models import (
    EvidenceQualityDecision,
    HorizonRegimeTrust,
    ModelPromotion,
    ModelRegressionCheck,
    Prediction,
    PredictionOutcome,
    PredictionTrustScore,
    PositiveRecommendationGateDecision,
    Stock,
)
from app.model_regression_detection import VERDICT_HEALTHY
from app.positive_recommendation_gate import (
    REASON_TRUST_QUALITY_TOO_LOW,
    VERDICT_GATE_PASS,
    VERDICT_GATE_SUPPRESSED,
)
from app.trust_dashboard import build_trust_dashboard, get_prediction_trust_drilldown

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


@pytest.fixture
def stock(session):
    s = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(s)
    session.flush()
    return s


def _make_prediction(session, stock, *, model_version=MODEL_VERSION, horizon_days=1):
    n = next(_counter)
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=horizon_days,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=model_version, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00") + Decimal(n % 10),
    )
    session.add(prediction)
    session.flush()
    return prediction


def test_empty_dashboard_for_unknown_model_version(session):
    snapshot = build_trust_dashboard(session, model_version="no-such-model")

    assert snapshot.model_version == "no-such-model"
    assert snapshot.trust_score_trend == ()
    assert snapshot.positive_recommendation_count == 0
    assert snapshot.successful_recommendation_count == 0
    assert snapshot.suppressed_candidate_count == 0
    assert snapshot.suppression_reason_counts == {}
    assert snapshot.evidence_quality_state_counts == {}


def test_counts_positive_successful_and_suppressed_candidates(session, stock):
    passed = _make_prediction(session, stock)
    session.add(PositiveRecommendationGateDecision(
        prediction_id=passed.id, verdict=VERDICT_GATE_PASS, evidence_quality_met=True, trust_quality_met=True,
        segment_trust_met=True, calibration_drift_met=True, suppression_reasons=[], evaluated_at=AS_OF,
        gate_rule_version="PRG-001",
    ))
    session.add(PredictionOutcome(
        prediction_id=passed.id, evaluation_date=AS_OF, highest_price=Decimal("110"), lowest_price=Decimal("99"),
        closing_price=Decimal("108"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.01"),
        actual_return=Decimal("0.08"), prediction_error=Decimal("0.01"), target_hit=True, stop_hit=False,
        outcome="SUCCESS",
    ))

    suppressed = _make_prediction(session, stock)
    session.add(PositiveRecommendationGateDecision(
        prediction_id=suppressed.id, verdict=VERDICT_GATE_SUPPRESSED, evidence_quality_met=True,
        trust_quality_met=False, segment_trust_met=True, calibration_drift_met=True,
        suppression_reasons=[REASON_TRUST_QUALITY_TOO_LOW], evaluated_at=AS_OF, gate_rule_version="PRG-001",
    ))
    session.commit()

    snapshot = build_trust_dashboard(session, model_version=MODEL_VERSION)

    assert snapshot.positive_recommendation_count == 1
    assert snapshot.successful_recommendation_count == 1
    assert snapshot.suppressed_candidate_count == 1
    assert snapshot.suppression_reason_counts == {REASON_TRUST_QUALITY_TOO_LOW: 1}


def test_only_latest_gate_decision_per_prediction_counts(session, stock):
    prediction = _make_prediction(session, stock)
    session.add(PositiveRecommendationGateDecision(
        prediction_id=prediction.id, verdict=VERDICT_GATE_SUPPRESSED, evidence_quality_met=False,
        trust_quality_met=False, segment_trust_met=True, calibration_drift_met=True,
        suppression_reasons=[REASON_TRUST_QUALITY_TOO_LOW], evaluated_at=AS_OF, gate_rule_version="PRG-001",
    ))
    session.commit()
    session.add(PositiveRecommendationGateDecision(
        prediction_id=prediction.id, verdict=VERDICT_GATE_PASS, evidence_quality_met=True, trust_quality_met=True,
        segment_trust_met=True, calibration_drift_met=True, suppression_reasons=[],
        evaluated_at=AS_OF.replace(month=2), gate_rule_version="PRG-001",
    ))
    session.commit()

    snapshot = build_trust_dashboard(session, model_version=MODEL_VERSION)

    assert snapshot.positive_recommendation_count == 1
    assert snapshot.suppressed_candidate_count == 0


def test_evidence_quality_state_counts_use_latest_decision(session, stock):
    prediction = _make_prediction(session, stock)
    session.add(EvidenceQualityDecision(
        prediction_id=prediction.id, state=STATE_INSUFFICIENT, available_category_count=1, stale_category_count=0,
        unavailable_category_count=4, categories_considered=["TECHNICAL_VOLUME"], leaked_categories=[], reasons=[],
        confidence_adjustment_ceiling=Decimal("0"), blocks_publication=True, evaluated_at=AS_OF,
        gate_rule_version="EQG-001",
    ))
    session.commit()
    session.add(EvidenceQualityDecision(
        prediction_id=prediction.id, state=STATE_SUFFICIENT, available_category_count=2, stale_category_count=0,
        unavailable_category_count=3, categories_considered=["TECHNICAL_VOLUME", "NEWS"], leaked_categories=[],
        reasons=[], confidence_adjustment_ceiling=prediction.confidence, blocks_publication=False,
        evaluated_at=AS_OF.replace(month=2), gate_rule_version="EQG-001",
    ))
    session.commit()

    snapshot = build_trust_dashboard(session, model_version=MODEL_VERSION)

    assert snapshot.evidence_quality_state_counts == {STATE_SUFFICIENT: 1}


def test_trust_score_trend_sorted_chronologically_across_predictions(session, stock):
    p1 = _make_prediction(session, stock)
    p2 = _make_prediction(session, stock)
    later = AS_OF.replace(year=2027, month=2)
    session.add(PredictionTrustScore(
        prediction_id=p2.id, overall_trust_score=Decimal("0.5"), trust_quality="MEDIUM", calibration_component=None,
        historical_accuracy_component=None, recent_performance_component=None, horizon_reliability_component=None,
        regime_reliability_component=None, evidence_quality_component=None, available_component_count=1,
        reasons=[], computed_at=later, trust_score_version="PTS-001",
    ))
    session.add(PredictionTrustScore(
        prediction_id=p1.id, overall_trust_score=Decimal("0.9"), trust_quality="HIGH", calibration_component=None,
        historical_accuracy_component=None, recent_performance_component=None, horizon_reliability_component=None,
        regime_reliability_component=None, evidence_quality_component=None, available_component_count=1,
        reasons=[], computed_at=AS_OF, trust_score_version="PTS-001",
    ))
    session.commit()

    snapshot = build_trust_dashboard(session, model_version=MODEL_VERSION)

    assert [s.prediction_id for s in snapshot.trust_score_trend] == [p1.id, p2.id]


def test_includes_promotion_and_regression_and_regime_trust_history(session, stock):
    session.add(ModelPromotion(
        candidate_model_version=MODEL_VERSION, baseline_model_version="old-model", evidence_report_version="CMC-001",
        success_rate_delta=Decimal("0.05"), decision="PROMOTED", decision_reason="IMPROVED", decided_at=AS_OF,
        approver="system", promotion_rule_version="MPR-001",
    ))
    session.add(ModelRegressionCheck(
        model_version=MODEL_VERSION, baseline_window_label="baseline", baseline_success_rate=Decimal("0.8"),
        baseline_sample_count=25, monitoring_window_label="monitoring", monitoring_success_rate=Decimal("0.8"),
        monitoring_sample_count=25, verdict=VERDICT_HEALTHY, segment_regressions=[], rollback_triggered=False,
        checked_at=AS_OF, detection_rule_version="MRD-001",
    ))
    session.add(HorizonRegimeTrust(
        model_version=MODEL_VERSION, segment_type=SEGMENT_COMBINED, horizon_days=1, regime="BULLISH_HIGH_VOL",
        sample_count=25, success_rate=Decimal("0.8"), success_rate_standard_error=Decimal("0.05"),
        verdict="SUFFICIENT_SAMPLE", is_low_trust=False, computed_at=AS_OF, trust_rule_version="HRT-001",
    ))
    session.commit()

    snapshot = build_trust_dashboard(session, model_version=MODEL_VERSION)

    assert len(snapshot.promotion_history) == 1
    assert len(snapshot.regression_history) == 1
    assert len(snapshot.regime_trust) == 1
    assert snapshot.regime_trust[0].regime == "BULLISH_HIGH_VOL"


def test_drilldown_returns_full_evidence_for_one_prediction(session, stock):
    prediction = _make_prediction(session, stock)
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("110"), lowest_price=Decimal("99"),
        closing_price=Decimal("108"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.01"),
        actual_return=Decimal("0.08"), prediction_error=Decimal("0.01"), target_hit=True, stop_hit=False,
        outcome="SUCCESS",
    ))
    session.add(PositiveRecommendationGateDecision(
        prediction_id=prediction.id, verdict=VERDICT_GATE_PASS, evidence_quality_met=True, trust_quality_met=True,
        segment_trust_met=True, calibration_drift_met=True, suppression_reasons=[], evaluated_at=AS_OF,
        gate_rule_version="PRG-001",
    ))
    session.commit()

    drilldown = get_prediction_trust_drilldown(session, prediction.id)

    assert drilldown.prediction.id == prediction.id
    assert drilldown.outcome.outcome == "SUCCESS"
    assert len(drilldown.gate_decision_history) == 1
    assert drilldown.gate_decision_history[0].verdict == VERDICT_GATE_PASS
    assert drilldown.attribution_snapshot is None
    assert drilldown.usefulness_assessment is None
