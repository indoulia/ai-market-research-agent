from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.confidence_calibration import MIN_SAMPLE_SIZE_FOR_COMPARISON, calibrate_confidence_for_prediction
from app.confidence_quality import (
    CONFIDENCE_QUALITY_VERSION,
    QUALITY_HIGH,
    QUALITY_INSUFFICIENT_DATA,
    QUALITY_LOW,
    QUALITY_MEDIUM,
    ConfidenceQualityImmutableError,
    classify_confidence_quality,
    get_confidence_quality,
)
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.outcomes import evaluate_recommendation

TRAIN_WINDOW = EvaluationWindow(
    label="training", start=datetime(2026, 1, 1, tzinfo=timezone.utc), end=datetime(2026, 1, 31, tzinfo=timezone.utc)
)
TARGET_AS_OF = datetime(2026, 2, 1, tzinfo=timezone.utc)


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


def _make_scan(session, scan_date):
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_evaluated(session, scan, symbol, *, as_of, confidence, win, price_timestamp=None):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=confidence, sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=as_of)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)

    close = Decimal("106") if win else Decimal("95")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=price_timestamp or (as_of + timedelta(days=1)),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    evaluate_recommendation(session, prediction)
    return prediction


def _seed_bucket(session, *, prefix, confidence, win_count, total):
    scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(total):
        _make_evaluated(session, scan, f"{prefix}{i}", as_of=as_of, confidence=confidence, win=(i < win_count))


def _target_prediction(session, *, confidence, price_timestamp=None):
    scan = _make_scan(session, date(2026, 2, 1))
    return _make_evaluated(
        session, scan, "TARGET", as_of=TARGET_AS_OF, confidence=confidence, win=True,
        price_timestamp=price_timestamp or (TARGET_AS_OF + timedelta(days=1)),
    )


def test_insufficient_sample_yields_insufficient_data_quality(session):
    prediction = _target_prediction(session, confidence=Decimal("0.85"))
    calibration = calibrate_confidence_for_prediction(session, prediction, training_window=TRAIN_WINDOW, calibrated_at=TARGET_AS_OF)

    classification = classify_confidence_quality(session, prediction, calibration, classified_at=TARGET_AS_OF)

    assert classification.quality == QUALITY_INSUFFICIENT_DATA
    assert any("historical setup count" in r for r in classification.reasons)


def test_high_confidence_with_weak_evidence_cannot_be_high_quality(session):
    # deliberately very high raw confidence, but zero supporting evidence
    prediction = _target_prediction(session, confidence=Decimal("0.99"))
    calibration = calibrate_confidence_for_prediction(session, prediction, training_window=TRAIN_WINDOW, calibrated_at=TARGET_AS_OF)

    classification = classify_confidence_quality(session, prediction, calibration, classified_at=TARGET_AS_OF)

    assert classification.quality != QUALITY_HIGH
    assert classification.quality == QUALITY_INSUFFICIENT_DATA


def test_strong_well_calibrated_fresh_evidence_yields_high_quality(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON * 2  # comfortably "strong"
    _seed_bucket(session, prefix="T", confidence=Decimal("0.85"), win_count=int(total * Decimal("0.85")), total=total)
    prediction = _target_prediction(session, confidence=Decimal("0.85"))
    calibration = calibrate_confidence_for_prediction(session, prediction, training_window=TRAIN_WINDOW, calibrated_at=TARGET_AS_OF)

    classification = classify_confidence_quality(session, prediction, calibration, classified_at=TARGET_AS_OF)

    assert classification.quality == QUALITY_HIGH
    assert classification.is_data_fresh is True


def test_adequate_but_not_strong_sample_yields_medium_quality(session):
    total = MIN_SAMPLE_SIZE_FOR_COMPARISON  # adequate, not strong (< 2x)
    _seed_bucket(session, prefix="T", confidence=Decimal("0.85"), win_count=int(total * Decimal("0.85")), total=total)
    prediction = _target_prediction(session, confidence=Decimal("0.85"))
    calibration = calibrate_confidence_for_prediction(session, prediction, training_window=TRAIN_WINDOW, calibrated_at=TARGET_AS_OF)

    classification = classify_confidence_quality(session, prediction, calibration, classified_at=TARGET_AS_OF)

    assert classification.quality == QUALITY_MEDIUM


def test_overconfident_calibration_yields_low_quality_despite_strong_sample(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON * 2
    _seed_bucket(session, prefix="T", confidence=Decimal("0.85"), win_count=int(total * Decimal("0.30")), total=total)
    prediction = _target_prediction(session, confidence=Decimal("0.85"))
    calibration = calibrate_confidence_for_prediction(session, prediction, training_window=TRAIN_WINDOW, calibrated_at=TARGET_AS_OF)

    classification = classify_confidence_quality(session, prediction, calibration, classified_at=TARGET_AS_OF)

    assert classification.quality == QUALITY_LOW


def test_stale_market_data_prevents_high_quality_even_with_strong_calibration(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON * 2
    _seed_bucket(session, prefix="T", confidence=Decimal("0.85"), win_count=int(total * Decimal("0.85")), total=total)
    prediction = _target_prediction(session, confidence=Decimal("0.85"), price_timestamp=TARGET_AS_OF - timedelta(days=5))
    calibration = calibrate_confidence_for_prediction(session, prediction, training_window=TRAIN_WINDOW, calibrated_at=TARGET_AS_OF)

    classification = classify_confidence_quality(session, prediction, calibration, classified_at=TARGET_AS_OF)

    assert classification.quality != QUALITY_HIGH
    assert classification.is_data_fresh is False


def test_quality_is_deterministic_and_idempotent(session):
    prediction = _target_prediction(session, confidence=Decimal("0.85"))
    calibration = calibrate_confidence_for_prediction(session, prediction, training_window=TRAIN_WINDOW, calibrated_at=TARGET_AS_OF)

    first = classify_confidence_quality(session, prediction, calibration, classified_at=TARGET_AS_OF)
    second = classify_confidence_quality(session, prediction, calibration, classified_at=TARGET_AS_OF)

    assert first.id == second.id
    assert get_confidence_quality(session, prediction.id).id == first.id


def test_classification_is_immutable_after_creation(session):
    prediction = _target_prediction(session, confidence=Decimal("0.85"))
    calibration = calibrate_confidence_for_prediction(session, prediction, training_window=TRAIN_WINDOW, calibrated_at=TARGET_AS_OF)
    classification = classify_confidence_quality(session, prediction, calibration, classified_at=TARGET_AS_OF)

    classification.quality = QUALITY_HIGH
    with pytest.raises(ConfidenceQualityImmutableError, match="quality"):
        session.flush()
    session.rollback()


def test_a_new_classification_version_produces_a_separate_row(session):
    prediction = _target_prediction(session, confidence=Decimal("0.85"))
    calibration = calibrate_confidence_for_prediction(session, prediction, training_window=TRAIN_WINDOW, calibrated_at=TARGET_AS_OF)

    v1 = classify_confidence_quality(session, prediction, calibration, classified_at=TARGET_AS_OF)
    v2 = classify_confidence_quality(
        session, prediction, calibration, classified_at=TARGET_AS_OF, classification_rule_version="CFQ-002"
    )

    assert v1.id != v2.id
    assert v1.classification_rule_version != v2.classification_rule_version
