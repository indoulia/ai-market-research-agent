from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adaptive_calibration import (
    CALIBRATION_CANDIDATE_VERSION,
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    VERDICT_IMPROVED,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_NOT_IMPROVED,
    apply_calibration_candidate,
    build_calibration_candidate,
    evaluate_calibration_candidate_out_of_sample,
)
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.market_regime import classify_market_regime
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from app.outcomes import evaluate_recommendation


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


def _make_evaluated(session, scan, symbol, *, as_of, predicted_probability, win: bool):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=predicted_probability,
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
        atr_percent=Decimal("0.035"),
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()

    discovery = record_discovery(
        session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="test", discovered_at=as_of
    )
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)

    close = Decimal("106") if win else Decimal("95")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=as_of + timedelta(days=1),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    evaluate_recommendation(session, prediction)
    return prediction


TRAIN_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
TRAIN_END = datetime(2026, 1, 31, tzinfo=timezone.utc)
EVAL_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
EVAL_END = datetime(2026, 6, 30, tzinfo=timezone.utc)


def test_overconfident_bucket_produces_a_negative_offset(session):
    scan = _make_scan(session, date(2026, 1, 10))
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        # predicted 0.95 but only 20% (4/20) succeed -> overconfident
        as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
        _make_evaluated(session, scan, f"S{i}", as_of=as_of, predicted_probability=Decimal("0.95"), win=(i < 4))

    window = EvaluationWindow(label="training", start=TRAIN_START, end=TRAIN_END)
    candidate = build_calibration_candidate(session, window)

    bucket = next(b for b in candidate.buckets if b.lower == Decimal("0.9"))
    assert candidate.version == CALIBRATION_CANDIDATE_VERSION
    assert bucket.calibration_error > 0
    adjusted = apply_calibration_candidate(candidate, Decimal("0.95"))
    assert adjusted < Decimal("0.95")


def test_bucket_without_enough_training_samples_is_not_adjusted(session):
    scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(3):
        _make_evaluated(session, scan, f"S{i}", as_of=as_of, predicted_probability=Decimal("0.95"), win=False)

    window = EvaluationWindow(label="training", start=TRAIN_START, end=TRAIN_END)
    candidate = build_calibration_candidate(session, window)

    adjusted = apply_calibration_candidate(candidate, Decimal("0.95"))
    assert adjusted == Decimal("0.95")


def test_out_of_sample_evaluation_rejects_overlapping_windows(session):
    window = EvaluationWindow(label="training", start=TRAIN_START, end=TRAIN_END)
    candidate = build_calibration_candidate(session, window)
    overlapping = EvaluationWindow(label="eval", start=TRAIN_END - timedelta(days=1), end=TRAIN_END + timedelta(days=30))

    with pytest.raises(OverlappingEvaluationWindowsError):
        evaluate_calibration_candidate_out_of_sample(session, candidate, overlapping)


def test_out_of_sample_evaluation_with_insufficient_samples(session):
    window = EvaluationWindow(label="training", start=TRAIN_START, end=TRAIN_END)
    candidate = build_calibration_candidate(session, window)
    eval_window = EvaluationWindow(label="eval", start=EVAL_START, end=EVAL_END)

    result = evaluate_calibration_candidate_out_of_sample(session, candidate, eval_window)

    assert result.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert result.raw_mean_absolute_error is None


def test_calibrated_candidate_improves_out_of_sample_error(session):
    train_scan = _make_scan(session, date(2026, 1, 10))
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
        # systematically overconfident: predicts 0.95, only 20% succeed
        _make_evaluated(session, train_scan, f"TRAIN{i}", as_of=as_of, predicted_probability=Decimal("0.95"), win=(i < 4))

    train_window = EvaluationWindow(label="training", start=TRAIN_START, end=TRAIN_END)
    candidate = build_calibration_candidate(session, train_window)

    eval_scan = _make_scan(session, date(2026, 6, 10))
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        as_of = datetime(2026, 6, 10, tzinfo=timezone.utc)
        # same systematic overconfidence pattern holds out-of-sample
        _make_evaluated(session, eval_scan, f"EVAL{i}", as_of=as_of, predicted_probability=Decimal("0.95"), win=(i < 4))

    eval_window = EvaluationWindow(label="eval", start=EVAL_START, end=EVAL_END)
    result = evaluate_calibration_candidate_out_of_sample(session, candidate, eval_window)

    assert result.evaluated_count == MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert result.candidate_mean_absolute_error < result.raw_mean_absolute_error
    assert result.verdict == VERDICT_IMPROVED


def test_candidate_that_does_not_generalize_is_not_improved(session):
    train_scan = _make_scan(session, date(2026, 1, 10))
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
        _make_evaluated(session, train_scan, f"TRAIN{i}", as_of=as_of, predicted_probability=Decimal("0.95"), win=(i < 4))

    train_window = EvaluationWindow(label="training", start=TRAIN_START, end=TRAIN_END)
    candidate = build_calibration_candidate(session, train_window)

    eval_scan = _make_scan(session, date(2026, 6, 10))
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        as_of = datetime(2026, 6, 10, tzinfo=timezone.utc)
        # out-of-sample the model is actually well-calibrated at 0.95 -- the
        # training-derived downward offset would now make things worse
        _make_evaluated(session, eval_scan, f"EVAL{i}", as_of=as_of, predicted_probability=Decimal("0.95"), win=True)

    eval_window = EvaluationWindow(label="eval", start=EVAL_START, end=EVAL_END)
    result = evaluate_calibration_candidate_out_of_sample(session, candidate, eval_window)

    assert result.verdict == VERDICT_NOT_IMPROVED


def test_horizon_breakdown_is_always_present_for_all_supported_horizons(session):
    scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, scan, f"S{i}", as_of=as_of, predicted_probability=Decimal("0.95"), win=(i < 4))

    window = EvaluationWindow(label="training", start=TRAIN_START, end=TRAIN_END)
    candidate = build_calibration_candidate(session, window)

    assert {h.horizon_days for h in candidate.by_horizon} == {1, 3, 5, 7}
    horizon_1 = next(h for h in candidate.by_horizon if h.horizon_days == 1)
    bucket = next(b for b in horizon_1.buckets if b.lower == Decimal("0.9"))
    assert bucket.sample_count == MIN_SAMPLE_SIZE_FOR_COMPARISON


def test_regime_calibration_is_reported_only_for_classified_scans(session):
    scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(6):
        _make_evaluated(session, scan, f"S{i}", as_of=as_of, predicted_probability=Decimal("0.72"), win=True)
    classify_market_regime(session, scan.id)

    window = EvaluationWindow(label="training", start=TRAIN_START, end=TRAIN_END)
    candidate = build_calibration_candidate(session, window)

    assert len(candidate.by_regime) == 1
    assert candidate.by_regime[0].sample_count == 6
