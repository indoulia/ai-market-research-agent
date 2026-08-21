from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.feature_drift_monitor import (
    FEATURE_DRIFT_VERSION,
    FEATURE_SMA20_DISTANCE,
    VERDICT_DRIFT_DETECTED,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_NO_DRIFT,
    InsufficientReferenceSampleError,
    UnknownFeatureError,
    UnknownReferenceDistributionError,
    detect_coverage_drift,
    detect_feature_drift,
    get_feature_drift_history,
    register_reference_distribution,
)
from app.models import DailyCandidateScan, ScanCandidate, Stock
from app.out_of_sample_validation import EvaluationWindow

MODEL_VERSION = "test-model-1"
BASE_DATE = date(2027, 1, 1)
REFERENCE_WINDOW = EvaluationWindow(
    label="reference", start=datetime(2027, 1, 1, tzinfo=timezone.utc), end=datetime(2027, 1, 30, tzinfo=timezone.utc)
)
MONITORING_WINDOW = EvaluationWindow(
    label="monitoring", start=datetime(2027, 2, 1, tzinfo=timezone.utc), end=datetime(2027, 2, 28, tzinfo=timezone.utc)
)
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


def _add_candidates(session, *, scan_date, model_version=MODEL_VERSION, count, sma20_distance, data_quality_passed=True):
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=count, excluded_count=0)
    session.add(scan)
    session.flush()
    for i in range(count):
        n = next(_counter)
        stock = Stock(symbol=f"S{n}", exchange="NSE", is_active=True)
        session.add(stock)
        session.flush()
        session.add(ScanCandidate(
            scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
            predicted_probability=Decimal("0.7"), confidence=Decimal("0.8"),
            sma20_distance=sma20_distance + Decimal(i) / Decimal("10000"),
            volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"),
            data_quality_passed=data_quality_passed, model_version=model_version, feature_version="FV-001",
        ))
    session.commit()


def test_register_reference_requires_minimum_sample(session):
    _add_candidates(session, scan_date=BASE_DATE, count=5, sma20_distance=Decimal("0.03"))

    with pytest.raises(InsufficientReferenceSampleError):
        register_reference_distribution(
            session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
            window=REFERENCE_WINDOW, registered_at=REFERENCE_WINDOW.start,
        )


def test_register_reference_idempotent(session):
    _add_candidates(session, scan_date=BASE_DATE, count=25, sma20_distance=Decimal("0.03"))

    first = register_reference_distribution(
        session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
        window=REFERENCE_WINDOW, registered_at=REFERENCE_WINDOW.start,
    )
    second = register_reference_distribution(
        session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
        window=REFERENCE_WINDOW, registered_at=REFERENCE_WINDOW.start,
    )

    assert first.id == second.id
    assert first.sample_count == 25
    assert first.reference_version == FEATURE_DRIFT_VERSION


def test_unknown_feature_raises(session):
    with pytest.raises(UnknownFeatureError):
        register_reference_distribution(
            session, model_version=MODEL_VERSION, feature_name="NOT_A_FEATURE",
            window=REFERENCE_WINDOW, registered_at=REFERENCE_WINDOW.start,
        )


def test_detect_feature_drift_raises_without_reference(session):
    with pytest.raises(UnknownReferenceDistributionError):
        detect_feature_drift(
            session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
            monitoring_window=MONITORING_WINDOW, evaluated_at=MONITORING_WINDOW.start,
        )


def test_no_drift_when_monitoring_close_to_reference(session):
    _add_candidates(session, scan_date=BASE_DATE, count=25, sma20_distance=Decimal("0.03"))
    register_reference_distribution(
        session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
        window=REFERENCE_WINDOW, registered_at=REFERENCE_WINDOW.start,
    )
    _add_candidates(session, scan_date=date(2027, 2, 1), count=25, sma20_distance=Decimal("0.031"))

    assessment = detect_feature_drift(
        session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
        monitoring_window=MONITORING_WINDOW, evaluated_at=MONITORING_WINDOW.start,
    )

    assert assessment.verdict == VERDICT_NO_DRIFT
    assert assessment.trust_reduction_recommended is False
    assert assessment.drift_rule_version == FEATURE_DRIFT_VERSION


def test_drift_detected_when_monitoring_far_from_reference(session):
    _add_candidates(session, scan_date=BASE_DATE, count=25, sma20_distance=Decimal("0.03"))
    register_reference_distribution(
        session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
        window=REFERENCE_WINDOW, registered_at=REFERENCE_WINDOW.start,
    )
    _add_candidates(session, scan_date=date(2027, 2, 1), count=25, sma20_distance=Decimal("0.50"))

    assessment = detect_feature_drift(
        session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
        monitoring_window=MONITORING_WINDOW, evaluated_at=MONITORING_WINDOW.start,
    )

    assert assessment.verdict == VERDICT_DRIFT_DETECTED
    assert assessment.trust_reduction_recommended is True


def test_insufficient_sample_when_monitoring_window_too_small(session):
    _add_candidates(session, scan_date=BASE_DATE, count=25, sma20_distance=Decimal("0.03"))
    register_reference_distribution(
        session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
        window=REFERENCE_WINDOW, registered_at=REFERENCE_WINDOW.start,
    )
    _add_candidates(session, scan_date=date(2027, 2, 1), count=3, sma20_distance=Decimal("0.50"))

    assessment = detect_feature_drift(
        session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
        monitoring_window=MONITORING_WINDOW, evaluated_at=MONITORING_WINDOW.start,
    )

    assert assessment.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert assessment.drift_magnitude is None


def test_feature_drift_idempotent(session):
    _add_candidates(session, scan_date=BASE_DATE, count=25, sma20_distance=Decimal("0.03"))
    register_reference_distribution(
        session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
        window=REFERENCE_WINDOW, registered_at=REFERENCE_WINDOW.start,
    )
    _add_candidates(session, scan_date=date(2027, 2, 1), count=25, sma20_distance=Decimal("0.031"))

    first = detect_feature_drift(
        session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
        monitoring_window=MONITORING_WINDOW, evaluated_at=MONITORING_WINDOW.start,
    )
    second = detect_feature_drift(
        session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE,
        monitoring_window=MONITORING_WINDOW, evaluated_at=MONITORING_WINDOW.start,
    )

    assert first.id == second.id
    assert len(get_feature_drift_history(session, model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE)) == 1


def test_coverage_drift_detected_when_coverage_drops(session):
    _add_candidates(session, scan_date=BASE_DATE, count=25, sma20_distance=Decimal("0.03"), data_quality_passed=True)
    _add_candidates(session, scan_date=date(2027, 2, 1), count=25, sma20_distance=Decimal("0.03"), data_quality_passed=False)

    assessment = detect_coverage_drift(
        session, model_version=MODEL_VERSION, reference_window=REFERENCE_WINDOW,
        monitoring_window=MONITORING_WINDOW, evaluated_at=MONITORING_WINDOW.start,
    )

    assert assessment.reference_coverage_rate == Decimal("1")
    assert assessment.monitoring_coverage_rate == Decimal("0")
    assert assessment.verdict == VERDICT_DRIFT_DETECTED
    assert assessment.trust_reduction_recommended is True


def test_coverage_drift_no_drift_when_stable(session):
    _add_candidates(session, scan_date=BASE_DATE, count=25, sma20_distance=Decimal("0.03"), data_quality_passed=True)
    _add_candidates(session, scan_date=date(2027, 2, 1), count=25, sma20_distance=Decimal("0.03"), data_quality_passed=True)

    assessment = detect_coverage_drift(
        session, model_version=MODEL_VERSION, reference_window=REFERENCE_WINDOW,
        monitoring_window=MONITORING_WINDOW, evaluated_at=MONITORING_WINDOW.start,
    )

    assert assessment.verdict == VERDICT_NO_DRIFT
    assert assessment.trust_reduction_recommended is False


def test_coverage_drift_insufficient_sample(session):
    _add_candidates(session, scan_date=BASE_DATE, count=3, sma20_distance=Decimal("0.03"), data_quality_passed=True)

    assessment = detect_coverage_drift(
        session, model_version=MODEL_VERSION, reference_window=REFERENCE_WINDOW,
        monitoring_window=MONITORING_WINDOW, evaluated_at=MONITORING_WINDOW.start,
    )

    assert assessment.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert assessment.coverage_rate_delta is None
