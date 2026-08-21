from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.feature_drift_monitor import FEATURE_SMA20_DISTANCE
from app.market_regime import classify_market_regime
from app.models import (
    DailyCandidateScan,
    FeatureDriftAssessment,
    MarketPrice,
    Prediction,
    PredictionOutcome,
    ScanCandidate,
    Stock,
)
from app.out_of_sample_validation import EvaluationWindow
from app.regime_transition_intelligence import (
    MissingCurrentRegimeError,
    REGIME_TRANSITION_VERSION,
    SOURCE_MARKET,
    SOURCE_MARKET_AND_MODEL,
    SOURCE_MODEL,
    SOURCE_NONE,
    VERDICT_NEAR_BOUNDARY,
    VERDICT_STABLE,
    detect_regime_transition,
    evaluate_transition_period_performance,
    get_regime_uncertainty_snapshot,
    snapshot_prediction_regime_uncertainty,
)

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
_stock_counter = iter(range(1000000))


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


def _make_scan_with_regime(session, *, scan_date, positive_count, total_count, atr_percent=Decimal("0.02")):
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=total_count, excluded_count=0)
    session.add(scan)
    session.flush()
    for i in range(total_count):
        n = next(_stock_counter)
        stock = Stock(symbol=f"S{n}", exchange="NSE", is_active=True)
        session.add(stock)
        session.flush()
        sma20 = Decimal("0.05") if i < positive_count else Decimal("-0.05")
        session.add(ScanCandidate(
            scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
            predicted_probability=Decimal("0.7"), confidence=Decimal("0.8"), sma20_distance=sma20,
            volume_ratio_20d=Decimal("1.10"), atr_percent=atr_percent, data_quality_passed=True,
            model_version=MODEL_VERSION, feature_version="FV-001",
        ))
    session.commit()
    classify_market_regime(session, scan.id)
    return scan


def _make_qualified_prediction(session, scan, symbol):
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
    return session.get(Prediction, generation.prediction_id)


def test_no_transition_when_no_previous_scan(session):
    scan = _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=8, total_count=10)

    assessment = detect_regime_transition(session, scan.id, detected_at=AS_OF)

    assert assessment.transition_detected is False
    assert assessment.previous_regime is None
    assert assessment.previous_scan_id is None
    assert assessment.assessment_rule_version == REGIME_TRANSITION_VERSION


def test_transition_detected_when_regime_changes(session):
    _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=2, total_count=10)  # BEARISH
    scan_2 = _make_scan_with_regime(session, scan_date=date(2027, 1, 2), positive_count=8, total_count=10)  # BULLISH

    assessment = detect_regime_transition(session, scan_2.id, detected_at=AS_OF)

    assert assessment.transition_detected is True
    assert assessment.previous_regime is not None
    assert assessment.previous_regime != assessment.current_regime


def test_missing_current_regime_raises(session):
    scan = DailyCandidateScan(scan_date=date(2027, 1, 1), universe_version="DCS-001", eligible_count=0, excluded_count=0)
    session.add(scan)
    session.commit()

    with pytest.raises(MissingCurrentRegimeError):
        detect_regime_transition(session, scan.id, detected_at=AS_OF)


def test_boundary_instability_near_threshold(session):
    # breadth = 6/10 = 0.60, exactly at BULLISH_BREADTH_THRESHOLD -> distance 0.
    scan = _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=6, total_count=10)

    assessment = detect_regime_transition(session, scan.id, detected_at=AS_OF)

    assert assessment.boundary_instability_verdict == VERDICT_NEAR_BOUNDARY


def test_boundary_stable_far_from_threshold(session):
    # breadth = 9/10 = 0.90, far from both thresholds.
    scan = _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=9, total_count=10)

    assessment = detect_regime_transition(session, scan.id, detected_at=AS_OF)

    assert assessment.boundary_instability_verdict == VERDICT_STABLE


def test_uncertainty_source_none_when_stable_and_no_drift(session):
    scan = _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=9, total_count=10)

    assessment = detect_regime_transition(session, scan.id, detected_at=AS_OF, model_version=MODEL_VERSION)

    assert assessment.uncertainty_source == SOURCE_NONE
    assert assessment.trust_reduction_recommended is False


def test_uncertainty_source_market_when_unstable_transition(session):
    _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=2, total_count=10)
    scan_2 = _make_scan_with_regime(session, scan_date=date(2027, 1, 2), positive_count=6, total_count=10)  # boundary + changed

    assessment = detect_regime_transition(session, scan_2.id, detected_at=AS_OF, model_version=MODEL_VERSION)

    assert assessment.uncertainty_source == SOURCE_MARKET
    assert assessment.trust_reduction_recommended is True


def test_uncertainty_source_model_when_drift_active_but_market_stable(session):
    scan = _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=9, total_count=10)
    session.add(FeatureDriftAssessment(
        model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE, monitoring_window_label="w",
        monitoring_sample_count=25, monitoring_mean=Decimal("0.5"), drift_magnitude=Decimal("3"),
        verdict="DRIFT_DETECTED", trust_reduction_recommended=True, evaluated_at=AS_OF, drift_rule_version="FDM-001",
    ))
    session.commit()

    assessment = detect_regime_transition(session, scan.id, detected_at=AS_OF, model_version=MODEL_VERSION)

    assert assessment.uncertainty_source == SOURCE_MODEL
    assert assessment.trust_reduction_recommended is False  # market alone isn't unstable; only market signal drives the trust flag


def test_uncertainty_source_market_and_model_when_both_active(session):
    _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=2, total_count=10)
    scan_2 = _make_scan_with_regime(session, scan_date=date(2027, 1, 2), positive_count=6, total_count=10)
    session.add(FeatureDriftAssessment(
        model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE, monitoring_window_label="w",
        monitoring_sample_count=25, monitoring_mean=Decimal("0.5"), drift_magnitude=Decimal("3"),
        verdict="DRIFT_DETECTED", trust_reduction_recommended=True, evaluated_at=AS_OF, drift_rule_version="FDM-001",
    ))
    session.commit()

    assessment = detect_regime_transition(session, scan_2.id, detected_at=AS_OF, model_version=MODEL_VERSION)

    assert assessment.uncertainty_source == SOURCE_MARKET_AND_MODEL


def test_regime_transition_idempotent(session):
    scan = _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=9, total_count=10)

    first = detect_regime_transition(session, scan.id, detected_at=AS_OF)
    second = detect_regime_transition(session, scan.id, detected_at=AS_OF)

    assert first.id == second.id


def test_snapshot_prediction_regime_uncertainty_none_without_assessment(session):
    scan = _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=9, total_count=10)
    prediction = _make_qualified_prediction(session, scan, "AAA")

    result = snapshot_prediction_regime_uncertainty(session, prediction, snapshotted_at=AS_OF)

    assert result is None


def test_snapshot_prediction_regime_uncertainty_links_and_idempotent(session):
    scan = _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=9, total_count=10)
    prediction = _make_qualified_prediction(session, scan, "AAA")
    detect_regime_transition(session, scan.id, detected_at=AS_OF)

    first = snapshot_prediction_regime_uncertainty(session, prediction, snapshotted_at=AS_OF)
    second = snapshot_prediction_regime_uncertainty(session, prediction, snapshotted_at=AS_OF)

    assert first is not None
    assert first.id == second.id
    assert get_regime_uncertainty_snapshot(session, prediction.id).id == first.id


def _add_outcome(session, prediction, outcome):
    session.add(PredictionOutcome(
        prediction_id=prediction.id, evaluation_date=AS_OF, highest_price=Decimal("110"), lowest_price=Decimal("99"),
        closing_price=Decimal("108"), maximum_return=Decimal("0.10"), maximum_drawdown=Decimal("-0.01"),
        actual_return=Decimal("0.08"), prediction_error=Decimal("0.01"), target_hit=(outcome == "SUCCESS"),
        stop_hit=(outcome == "FAILURE"), outcome=outcome,
    ))
    session.commit()


def test_transition_period_performance_insufficient_sample(session):
    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=1))

    report = evaluate_transition_period_performance(session, window=window, computed_at=AS_OF)

    assert report.verdict == "INSUFFICIENT_SAMPLE"
    assert report.success_rate_delta is None
    assert report.report_rule_version == REGIME_TRANSITION_VERSION


def test_transition_period_performance_measured(session):
    stable_scan = _make_scan_with_regime(session, scan_date=date(2027, 1, 1), positive_count=9, total_count=10)
    detect_regime_transition(session, stable_scan.id, detected_at=AS_OF)
    for i in range(20):
        p = _make_qualified_prediction(session, stable_scan, f"ST{i}")
        _add_outcome(session, p, "SUCCESS")

    _make_scan_with_regime(session, scan_date=date(2027, 1, 2), positive_count=2, total_count=10)
    transition_scan = _make_scan_with_regime(session, scan_date=date(2027, 1, 3), positive_count=8, total_count=10)
    detect_regime_transition(session, transition_scan.id, detected_at=AS_OF)
    for i in range(20):
        p = _make_qualified_prediction(session, transition_scan, f"TR{i}")
        _add_outcome(session, p, "FAILURE")

    window = EvaluationWindow(label="w", start=AS_OF - timedelta(days=1), end=AS_OF + timedelta(days=1))
    report = evaluate_transition_period_performance(session, window=window, computed_at=AS_OF)

    assert report.verdict == "MEASURED"
    assert report.stable_success_rate == Decimal("1")
    assert report.transition_success_rate == Decimal("0")
    assert report.success_rate_delta == Decimal("-1")
