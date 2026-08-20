from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.discovery_effectiveness import VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK
from app.feedback_learning_signals import (
    FEEDBACK_LEARNING_SIGNAL_VERSION,
    REPEATED_PATTERN_MIN_DISTINCT_USERS,
    compute_feedback_learning_signals,
)
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcome_measurement import measure_outcome
from app.outcomes import evaluate_recommendation
from app.recommendation_feedback import CATEGORY_TARGET, REASON_AGREE, REASON_TOO_HIGH, submit_feedback
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

AS_OF = datetime(2026, 9, 1, tzinfo=timezone.utc)


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


def _make_evaluated(session, scan, symbol, *, as_of, win: bool):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
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
    measure_outcome(session, outcome, measured_at=as_of)
    return prediction


def test_insufficient_feedback_sample_is_explicitly_reported(session):
    scan = _make_scan(session, date(2026, 9, 1))
    prediction = _make_evaluated(session, scan, "AAA", as_of=AS_OF, win=True)
    submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH, submitted_at=AS_OF)

    report = compute_feedback_learning_signals(session)

    signal = next(s for s in report.signals if s.category == CATEGORY_TARGET and s.reason_code == REASON_TOO_HIGH)
    assert signal.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert signal.evaluated_count == 1


def test_feedback_predictive_of_failure_is_flagged_weak(session):
    scan = _make_scan(session, date(2026, 9, 1))
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(total):
        # "TOO_HIGH" feedback consistently precedes a failed recommendation
        prediction = _make_evaluated(session, scan, f"F{i}", as_of=AS_OF, win=False)
        submit_feedback(session, prediction, user_id=f"user-{i}", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH, submitted_at=AS_OF)
    for i in range(total):
        # "AGREE" feedback on winners, as a strong baseline
        prediction = _make_evaluated(session, scan, f"S{i}", as_of=AS_OF, win=True)
        submit_feedback(session, prediction, user_id=f"user-s{i}", category=CATEGORY_TARGET, reason_code=REASON_AGREE, submitted_at=AS_OF)

    report = compute_feedback_learning_signals(session)

    too_high = next(s for s in report.signals if s.reason_code == REASON_TOO_HIGH)
    agree = next(s for s in report.signals if s.reason_code == REASON_AGREE)
    assert too_high.success_rate == Decimal("0")
    assert too_high.verdict == VERDICT_WEAK
    assert agree.success_rate == Decimal("1")
    assert agree.verdict == VERDICT_OK


def test_repeated_feedback_pattern_is_detected(session):
    scan = _make_scan(session, date(2026, 9, 1))
    prediction = _make_evaluated(session, scan, "AAA", as_of=AS_OF, win=True)
    submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH, submitted_at=AS_OF)
    submit_feedback(session, prediction, user_id="user-2", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH, submitted_at=AS_OF)
    assert REPEATED_PATTERN_MIN_DISTINCT_USERS == 2

    report = compute_feedback_learning_signals(session)

    signal = next(s for s in report.signals if s.reason_code == REASON_TOO_HIGH)
    assert signal.distinct_user_count == 2
    assert signal.distinct_prediction_count == 1
    assert signal.total_feedback_count == 2
    assert signal.repeated_prediction_count == 1


def test_a_single_prediction_is_only_counted_once_per_signal_despite_multiple_feedback(session):
    scan = _make_scan(session, date(2026, 9, 1))
    prediction = _make_evaluated(session, scan, "AAA", as_of=AS_OF, win=True)
    submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH, submitted_at=AS_OF)
    submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH, submitted_at=AS_OF + timedelta(hours=1))

    report = compute_feedback_learning_signals(session)

    signal = next(s for s in report.signals if s.reason_code == REASON_TOO_HIGH)
    assert signal.total_feedback_count == 2
    assert signal.evaluated_count == 1  # one prediction, counted once


def test_open_recommendation_is_excluded_from_evaluated_count(session):
    scan = _make_scan(session, date(2026, 9, 1))
    stock = Stock(symbol="OPEN1", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_TARGET, reason_code=REASON_TOO_HIGH, submitted_at=AS_OF)

    report = compute_feedback_learning_signals(session)

    signal = next(s for s in report.signals if s.reason_code == REASON_TOO_HIGH)
    assert signal.distinct_prediction_count == 1
    assert signal.evaluated_count == 0
    assert signal.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_aggregation_by_horizon_and_model_and_score_band(session):
    scan = _make_scan(session, date(2026, 9, 1))
    prediction = _make_evaluated(session, scan, "AAA", as_of=AS_OF, win=True)
    submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_TARGET, reason_code=REASON_AGREE, submitted_at=AS_OF)

    report = compute_feedback_learning_signals(session)

    assert any(s.key == str(prediction.horizon_days) for s in report.by_horizon)
    assert any(s.key == prediction.model_version for s in report.by_model_version)
    assert len(report.by_score_band) >= 1


def test_report_is_versioned_and_never_writes_to_predictions(session):
    scan = _make_scan(session, date(2026, 9, 1))
    prediction = _make_evaluated(session, scan, "AAA", as_of=AS_OF, win=True)
    submit_feedback(session, prediction, user_id="user-1", category=CATEGORY_TARGET, reason_code=REASON_AGREE, submitted_at=AS_OF)
    before = (prediction.opportunity_score, prediction.predicted_probability)

    report = compute_feedback_learning_signals(session)

    after = (prediction.opportunity_score, prediction.predicted_probability)
    assert report.version == FEEDBACK_LEARNING_SIGNAL_VERSION
    assert before == after
