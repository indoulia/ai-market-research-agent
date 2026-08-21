from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.confidence_analysis import VERDICT_WELL_CALIBRATED
from app.confidence_quality import QUALITY_HIGH, QUALITY_INSUFFICIENT_DATA, QUALITY_LOW, QUALITY_MEDIUM
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import evaluate_evidence_quality
from app.evidence_snapshot import capture_evidence_snapshot
from app.model_regression_detection import DETECTION_RULE_VERSION, VERDICT_HEALTHY
from app.models import (
    ConfidenceCalibrationRecord,
    ConfidenceQualityClassification,
    DailyCandidateScan,
    HorizonProbabilityProfile,
    MarketPrice,
    ModelRegressionCheck,
    Prediction,
    RecommendationEvidenceItem,
    ScanCandidate,
    Stock,
)
from app.outcomes import evaluate_recommendation
from app.prediction_trust_score import (
    PREDICTION_TRUST_SCORE_VERSION,
    REASON_EVIDENCE_LEAKAGE_DETECTED,
    REASON_NO_COMPONENTS_AVAILABLE,
    REASON_TOO_FEW_COMPONENTS_AVAILABLE,
    PredictionTrustScoreImmutableError,
    compute_prediction_trust_score,
    get_trust_score_history,
)
from app.short_horizon_probability import PROBABILITY_PROFILE_VERSION, VERDICT_CALIBRATED
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2026, 10, 1, tzinfo=timezone.utc)
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


def _make_scan(session):
    scan_date = date(2026, 10, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_evaluated(session, scan, symbol, *, win: bool, gate_sufficient: bool | None):
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

    if gate_sufficient is not None:
        capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
        decision = evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)
        if gate_sufficient:
            assert decision.state == "SUFFICIENT"
        else:
            assert decision.state != "SUFFICIENT"

    close = Decimal("106") if win else Decimal("95")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    evaluate_recommendation(session, prediction)
    return prediction


def _add_confidence_quality(session, prediction, quality):
    calibration = ConfidenceCalibrationRecord(
        prediction_id=prediction.id, calibration_version="CC-TEST", raw_confidence=prediction.confidence,
        calibrated_confidence=prediction.confidence, bucket_lower=Decimal("0.7"), bucket_upper=Decimal("0.8"),
        sample_count=MIN_SAMPLE_SIZE_FOR_COMPARISON, calibration_error=Decimal("0"), verdict=VERDICT_WELL_CALIBRATED,
        training_window_label="test", calibrated_at=AS_OF,
    )
    session.add(calibration)
    session.flush()
    session.add(ConfidenceQualityClassification(
        prediction_id=prediction.id, confidence_calibration_record_id=calibration.id, quality=quality,
        reasons=["test"], sample_count=MIN_SAMPLE_SIZE_FOR_COMPARISON, calibration_verdict=VERDICT_WELL_CALIBRATED,
        is_data_fresh=True, classified_at=AS_OF, classification_rule_version="CFQ-001",
    ))
    session.commit()


def _add_regression_check(session, verdict):
    session.add(ModelRegressionCheck(
        model_version=MODEL_VERSION, baseline_window_label="baseline", baseline_success_rate=Decimal("1"),
        baseline_sample_count=MIN_SAMPLE_SIZE_FOR_COMPARISON, monitoring_window_label="monitoring",
        monitoring_success_rate=Decimal("1") if verdict == VERDICT_HEALTHY else Decimal("0"),
        monitoring_sample_count=MIN_SAMPLE_SIZE_FOR_COMPARISON, verdict=verdict, segment_regressions=[],
        rollback_triggered=(verdict != VERDICT_HEALTHY), checked_at=AS_OF, detection_rule_version=DETECTION_RULE_VERSION,
    ))
    session.commit()


def _add_horizon_profile(session, *, target_hit_probability):
    session.add(HorizonProbabilityProfile(
        model_version=MODEL_VERSION, horizon_days=1, sample_count=MIN_SAMPLE_SIZE_FOR_COMPARISON,
        positive_return_probability=target_hit_probability, target_hit_probability=target_hit_probability,
        stop_hit_probability=Decimal("1") - target_hit_probability, expected_return=Decimal("0.03"),
        downside_p10_return=Decimal("-0.03"), verdict=VERDICT_CALIBRATED, computed_at=AS_OF,
        profile_rule_version=PROBABILITY_PROFILE_VERSION,
    ))
    session.commit()


def test_no_components_available_is_insufficient_data(session):
    scan = _make_scan(session)
    prediction = _make_evaluated(session, scan, "A1", win=True, gate_sufficient=None)

    score = compute_prediction_trust_score(session, prediction, computed_at=AS_OF)

    assert score.trust_quality == QUALITY_INSUFFICIENT_DATA
    assert score.overall_trust_score is None
    assert score.available_component_count == 0
    assert score.reasons == [REASON_NO_COMPONENTS_AVAILABLE]
    assert score.trust_score_version == PREDICTION_TRUST_SCORE_VERSION


def test_evidence_leakage_forces_insufficient_data(session):
    scan = _make_scan(session)
    prediction = _make_evaluated(session, scan, "B1", win=True, gate_sufficient=None)
    session.add(RecommendationEvidenceItem(
        prediction_id=prediction.id, evidence_category="NEWS", status="AVAILABLE", source="test-leak",
        reference="future", evidence_timestamp=AS_OF + timedelta(days=10), is_stale=False,
        snapshot_rule_version="RES-001", captured_at=AS_OF,
    ))
    session.commit()
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)
    _add_confidence_quality(session, prediction, QUALITY_HIGH)  # even with other good evidence present

    score = compute_prediction_trust_score(session, prediction, computed_at=AS_OF)

    assert score.trust_quality == QUALITY_INSUFFICIENT_DATA
    assert score.overall_trust_score is None
    assert score.reasons == [REASON_EVIDENCE_LEAKAGE_DETECTED]


def test_few_components_available_caps_trust_quality(session):
    scan = _make_scan(session)
    prediction = _make_evaluated(session, scan, "C1", win=True, gate_sufficient=True)
    _add_confidence_quality(session, prediction, QUALITY_HIGH)
    _add_regression_check(session, VERDICT_HEALTHY)
    # deliberately no historical-accuracy sample, no horizon profile, no regime sample

    score = compute_prediction_trust_score(session, prediction, computed_at=AS_OF)

    assert score.available_component_count == 3  # calibration, recent_performance, evidence_quality
    assert score.overall_trust_score == Decimal("1")
    assert score.trust_quality == QUALITY_MEDIUM  # capped despite a perfect average
    assert REASON_TOO_FEW_COMPONENTS_AVAILABLE in score.reasons


def test_full_evidence_yields_high_trust(session):
    scan = _make_scan(session)
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON
    predictions = [_make_evaluated(session, scan, f"D{i}", win=True, gate_sufficient=True) for i in range(total)]
    subject = predictions[0]

    _add_confidence_quality(session, subject, QUALITY_HIGH)
    _add_regression_check(session, VERDICT_HEALTHY)
    _add_horizon_profile(session, target_hit_probability=Decimal("0.9"))

    score = compute_prediction_trust_score(session, subject, computed_at=AS_OF)

    assert score.available_component_count == 6
    assert score.calibration_component == Decimal("1")
    assert score.historical_accuracy_component == Decimal("1")
    assert score.recent_performance_component == Decimal("1")
    assert score.horizon_reliability_component == Decimal("0.9")
    assert score.regime_reliability_component == Decimal("1")
    assert score.evidence_quality_component == Decimal("1")
    expected = (Decimal("1") + Decimal("1") + Decimal("1") + Decimal("0.9") + Decimal("1") + Decimal("1")) / Decimal("6")
    assert abs(score.overall_trust_score - expected) < Decimal("0.0000001")
    assert score.trust_quality == QUALITY_HIGH
    assert score.reasons == []


def test_recalculation_reflects_new_evidence(session):
    scan = _make_scan(session)
    prediction = _make_evaluated(session, scan, "E1", win=True, gate_sufficient=None)

    first = compute_prediction_trust_score(session, prediction, computed_at=AS_OF)
    assert first.trust_quality == QUALITY_INSUFFICIENT_DATA

    # new evidence becomes available since the first computation --
    # a confidence-quality classification is produced independently of
    # M1.74 gating/price-data timing, so it cleanly demonstrates
    # recalculation without touching the leakage-detection path.
    _add_confidence_quality(session, prediction, QUALITY_LOW)

    second = compute_prediction_trust_score(session, prediction, computed_at=AS_OF + timedelta(hours=1))

    assert second.id != first.id
    assert second.trust_quality != QUALITY_INSUFFICIENT_DATA
    assert second.available_component_count == 1
    assert len(get_trust_score_history(session, prediction.id)) == 2


def test_idempotent_per_prediction_and_computed_at(session):
    scan = _make_scan(session)
    prediction = _make_evaluated(session, scan, "F1", win=True, gate_sufficient=None)

    first = compute_prediction_trust_score(session, prediction, computed_at=AS_OF)
    second = compute_prediction_trust_score(session, prediction, computed_at=AS_OF)

    assert first.id == second.id
    assert len(get_trust_score_history(session, prediction.id)) == 1


def test_score_is_immutable(session):
    scan = _make_scan(session)
    prediction = _make_evaluated(session, scan, "G1", win=True, gate_sufficient=None)
    score = compute_prediction_trust_score(session, prediction, computed_at=AS_OF)

    score.trust_quality = QUALITY_HIGH
    with pytest.raises(PredictionTrustScoreImmutableError):
        session.commit()
    session.rollback()


def test_never_writes_to_prediction(session):
    scan = _make_scan(session)
    prediction = _make_evaluated(session, scan, "H1", win=True, gate_sufficient=None)
    before = (prediction.confidence, prediction.opportunity_score)

    compute_prediction_trust_score(session, prediction, computed_at=AS_OF)

    after = (prediction.confidence, prediction.opportunity_score)
    assert before == after
