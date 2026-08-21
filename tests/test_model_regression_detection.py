from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.model_regression_detection import (
    DETECTION_RULE_VERSION,
    VERDICT_HEALTHY,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_REGRESSED,
    detect_model_regression,
    get_regression_history,
)
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from app.outcomes import evaluate_recommendation
from app.trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

MODEL_VERSION = "test-model-1"
BASELINE_WINDOW = EvaluationWindow(
    label="baseline", start=datetime(2026, 1, 1, tzinfo=timezone.utc), end=datetime(2026, 1, 31, tzinfo=timezone.utc)
)
MONITORING_WINDOW = EvaluationWindow(
    label="monitoring", start=datetime(2026, 6, 1, tzinfo=timezone.utc), end=datetime(2026, 6, 30, tzinfo=timezone.utc)
)
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


def _make_scan(session, scan_date):
    scan_date = scan_date + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_evaluated(session, scan, symbol, *, as_of, win: bool, model_version=MODEL_VERSION):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version=model_version, feature_version="FV-001",
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
    evaluate_recommendation(session, prediction)
    return prediction


def _seed(session, *, scan_date, as_of, win_count, total, prefix):
    scan = _make_scan(session, scan_date)
    for i in range(total):
        _make_evaluated(session, scan, f"{prefix}{i}", as_of=as_of, win=(i < win_count))


def test_insufficient_sample_produces_no_unsafe_conclusion(session):
    check = detect_model_regression(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, checked_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    assert check.verdict == VERDICT_INSUFFICIENT_SAMPLE
    assert check.detection_rule_version == DETECTION_RULE_VERSION
    assert check.rollback_triggered is False


def test_stable_performance_is_healthy(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed(session, scan_date=date(2026, 1, 10), as_of=datetime(2026, 1, 10, tzinfo=timezone.utc), win_count=total // 2, total=total, prefix="B")
    _seed(session, scan_date=date(2026, 6, 10), as_of=datetime(2026, 6, 10, tzinfo=timezone.utc), win_count=total // 2, total=total, prefix="M")

    check = detect_model_regression(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, checked_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    assert check.verdict == VERDICT_HEALTHY
    assert check.rollback_triggered is False


def test_real_degradation_is_detected_and_triggers_rollback(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed(session, scan_date=date(2026, 1, 10), as_of=datetime(2026, 1, 10, tzinfo=timezone.utc), win_count=total, total=total, prefix="B")
    _seed(session, scan_date=date(2026, 6, 10), as_of=datetime(2026, 6, 10, tzinfo=timezone.utc), win_count=0, total=total, prefix="M")

    check = detect_model_regression(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, checked_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    assert check.verdict == VERDICT_REGRESSED
    assert check.rollback_triggered is True
    assert check.baseline_success_rate == Decimal("1")
    assert check.monitoring_success_rate == Decimal("0")


def test_overlapping_windows_are_rejected(session):
    overlapping = EvaluationWindow(label="overlap", start=BASELINE_WINDOW.end - timedelta(days=1), end=MONITORING_WINDOW.start)

    with pytest.raises(OverlappingEvaluationWindowsError):
        detect_model_regression(
            session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
            monitoring_window=overlapping, checked_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )


def test_a_different_model_version_is_isolated(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed(session, scan_date=date(2026, 1, 10), as_of=datetime(2026, 1, 10, tzinfo=timezone.utc), win_count=total, total=total, prefix="B")
    # a different model's data should not leak into this model's check
    scan = _make_scan(session, date(2026, 6, 10))
    for i in range(total):
        _make_evaluated(session, scan, f"O{i}", as_of=datetime(2026, 6, 10, tzinfo=timezone.utc), win=False, model_version="other-model")

    check = detect_model_regression(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, checked_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    assert check.verdict == VERDICT_INSUFFICIENT_SAMPLE  # no monitoring-window data for THIS model version


def test_regression_history_is_retained(session):
    detect_model_regression(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, checked_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    detect_model_regression(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, checked_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
    )

    history = get_regression_history(session, MODEL_VERSION)
    assert len(history) == 2


def test_detection_never_writes_to_predictions(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed(session, scan_date=date(2026, 1, 10), as_of=datetime(2026, 1, 10, tzinfo=timezone.utc), win_count=total, total=total, prefix="B")
    before = {p.id: p.opportunity_score for p in session.query(Prediction).all()}

    detect_model_regression(
        session, model_version=MODEL_VERSION, baseline_window=BASELINE_WINDOW,
        monitoring_window=MONITORING_WINDOW, checked_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    after = {p.id: p.opportunity_score for p in session.query(Prediction).all()}
    assert before == after
