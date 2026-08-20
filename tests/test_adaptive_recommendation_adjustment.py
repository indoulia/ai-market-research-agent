from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adaptive_recommendation_adjustment import (
    ADAPTIVE_ADJUSTMENT_VERSION,
    SOURCE_FEEDBACK_LEARNING_SIGNAL,
    SOURCE_PROBABILITY_CALIBRATION,
    SOURCE_REGIME_SCORE_ADJUSTMENT,
    STATUS_PENDING,
    STATUS_VALIDATED,
    generate_adaptive_adjustment_candidates,
)
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.out_of_sample_validation import EvaluationWindow
from app.outcome_measurement import measure_outcome
from app.outcomes import evaluate_recommendation
from app.recommendation_feedback import CATEGORY_TARGET, REASON_AGREE, REASON_TOO_HIGH, submit_feedback
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

TRAIN_WINDOW = EvaluationWindow(
    label="training", start=datetime(2026, 1, 1, tzinfo=timezone.utc), end=datetime(2026, 1, 31, tzinfo=timezone.utc)
)
EVAL_WINDOW = EvaluationWindow(
    label="eval", start=datetime(2026, 6, 1, tzinfo=timezone.utc), end=datetime(2026, 6, 30, tzinfo=timezone.utc)
)


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


def _make_scan(session, scan_date, eligible_count=1):
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=eligible_count, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_evaluated(session, scan, symbol, *, as_of, predicted_probability=Decimal("0.72"),
                     sma20_distance=Decimal("0.03"), win: bool, measure_m38=False):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=predicted_probability, confidence=Decimal("0.80"), sma20_distance=sma20_distance,
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
        stock_id=stock.id, timestamp=as_of + timedelta(days=1),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    outcome = evaluate_recommendation(session, prediction)
    if measure_m38:
        measure_outcome(session, outcome, measured_at=as_of)
    return prediction


def test_no_evidence_produces_no_candidates(session):
    report = generate_adaptive_adjustment_candidates(session, training_window=TRAIN_WINDOW, evaluation_window=EVAL_WINDOW)

    assert report.candidates == ()
    assert report.version == ADAPTIVE_ADJUSTMENT_VERSION


def test_overconfident_calibration_pattern_is_validated_out_of_sample(session):
    train_scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(20):
        _make_evaluated(session, train_scan, f"TRAIN{i}", as_of=as_of, predicted_probability=Decimal("0.95"), win=(i < 4))

    eval_scan = _make_scan(session, date(2026, 6, 10))
    eval_as_of = datetime(2026, 6, 10, tzinfo=timezone.utc)
    for i in range(20):
        _make_evaluated(session, eval_scan, f"EVAL{i}", as_of=eval_as_of, predicted_probability=Decimal("0.95"), win=(i < 4))

    report = generate_adaptive_adjustment_candidates(session, training_window=TRAIN_WINDOW, evaluation_window=EVAL_WINDOW)

    candidate = next(c for c in report.candidates if c.source_signal == SOURCE_PROBABILITY_CALIBRATION)
    assert candidate.validation_status == STATUS_VALIDATED
    assert candidate.sample_size == 20
    assert "overconfident" in candidate.rationale.lower()


def test_regime_miscalibration_pattern_produces_a_candidate(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON * 2
    train_scan = _make_scan(session, date(2026, 1, 10), eligible_count=total)
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(total):
        # bullish/high-vol breadth via positive sma20_distance + atr_percent=0.035
        _make_evaluated(session, train_scan, f"T{i}", as_of=as_of, win=(i < total // 8))

    eval_scan = _make_scan(session, date(2026, 6, 10), eligible_count=total)
    eval_as_of = datetime(2026, 6, 10, tzinfo=timezone.utc)
    for i in range(total):
        _make_evaluated(session, eval_scan, f"E{i}", as_of=eval_as_of, win=(i < total // 8))

    report = generate_adaptive_adjustment_candidates(session, training_window=TRAIN_WINDOW, evaluation_window=EVAL_WINDOW)

    regime_candidates = [c for c in report.candidates if c.source_signal == SOURCE_REGIME_SCORE_ADJUSTMENT]
    assert len(regime_candidates) == 1
    assert regime_candidates[0].sample_size == total


def test_weak_feedback_signal_is_surfaced_as_pending(session):
    scan = _make_scan(session, date(2026, 9, 1))
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        prediction = _make_evaluated(session, scan, f"F{i}", as_of=as_of, win=False, measure_m38=True)
        submit_feedback(session, prediction, user_id=f"user-{i}", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH, submitted_at=as_of)
    for i in range(total):
        prediction = _make_evaluated(session, scan, f"S{i}", as_of=as_of, win=True, measure_m38=True)
        submit_feedback(session, prediction, user_id=f"user-s{i}", category=CATEGORY_TARGET, reason_code=REASON_AGREE, submitted_at=as_of)

    report = generate_adaptive_adjustment_candidates(session, training_window=TRAIN_WINDOW, evaluation_window=EVAL_WINDOW)

    feedback_candidates = [c for c in report.candidates if c.source_signal == SOURCE_FEEDBACK_LEARNING_SIGNAL]
    # only the TOO_HIGH-on-failures group should be weak enough to surface
    assert len(feedback_candidates) >= 1
    assert all(c.validation_status == STATUS_PENDING for c in feedback_candidates)


def test_candidates_never_write_to_predictions(session):
    train_scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(20):
        _make_evaluated(session, train_scan, f"TRAIN{i}", as_of=as_of, predicted_probability=Decimal("0.95"), win=(i < 4))
    before = {p.id: (p.opportunity_score, p.predicted_probability, p.confidence) for p in session.query(Prediction).all()}

    generate_adaptive_adjustment_candidates(session, training_window=TRAIN_WINDOW, evaluation_window=EVAL_WINDOW)

    after = {p.id: (p.opportunity_score, p.predicted_probability, p.confidence) for p in session.query(Prediction).all()}
    assert before == after


def test_report_generation_is_reproducible(session):
    train_scan = _make_scan(session, date(2026, 1, 10))
    as_of = datetime(2026, 1, 10, tzinfo=timezone.utc)
    for i in range(20):
        _make_evaluated(session, train_scan, f"TRAIN{i}", as_of=as_of, predicted_probability=Decimal("0.95"), win=(i < 4))
    eval_scan = _make_scan(session, date(2026, 6, 10))
    eval_as_of = datetime(2026, 6, 10, tzinfo=timezone.utc)
    for i in range(20):
        _make_evaluated(session, eval_scan, f"EVAL{i}", as_of=eval_as_of, predicted_probability=Decimal("0.95"), win=(i < 4))

    first = generate_adaptive_adjustment_candidates(session, training_window=TRAIN_WINDOW, evaluation_window=EVAL_WINDOW)
    second = generate_adaptive_adjustment_candidates(session, training_window=TRAIN_WINDOW, evaluation_window=EVAL_WINDOW)

    assert first == second
