from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, SOURCE_WATCHLIST, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcomes import evaluate_recommendation
from app.out_of_sample_validation import (
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    OOS_VALIDATION_VERSION,
    REGRESSION_MARGIN,
    VERDICT_INSUFFICIENT_EVIDENCE,
    VERDICT_REGRESSED,
    VERDICT_VALIDATED,
    EvaluationWindow,
    OverlappingEvaluationWindowsError,
    compare_out_of_sample_windows,
    compute_out_of_sample_report,
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


def _make_stock(session, symbol):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _make_scan(session, scan_date):
    from sqlalchemy import select

    existing = session.scalar(
        select(DailyCandidateScan).where(
            DailyCandidateScan.scan_date == scan_date, DailyCandidateScan.universe_version == "DCS-001"
        )
    )
    if existing is not None:
        return existing
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_evaluated(session, symbol, *, source, as_of, win: bool, horizon_days=1):
    scan = _make_scan(session, as_of.date())
    stock = _make_stock(session, symbol)
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=Decimal("0.72"),
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
        session, scan_id=scan.id, stock_id=stock.id, source=source, rationale="test", discovered_at=as_of
    )
    generation = route_discovery_through_pipeline(
        session,
        discovery,
        as_of_timestamp=as_of,
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)

    filler = [100] * (horizon_days - 1)
    closes = filler + ([106] if win else [95])
    for offset, close in enumerate(closes, start=1):
        close = Decimal(str(close))
        session.add(MarketPrice(
            stock_id=stock.id,
            timestamp=as_of + timedelta(days=offset),
            open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
            volume=1000, source="test",
        ))
    session.flush()
    evaluate_recommendation(session, prediction)
    return prediction


EARLY = datetime(2026, 1, 10, tzinfo=timezone.utc)
LATE = datetime(2026, 6, 10, tzinfo=timezone.utc)


def test_empty_window_is_insufficient_evidence(session):
    window = EvaluationWindow(label="empty", start=None, end=None)

    report = compute_out_of_sample_report(session, window)

    assert report.report_version == OOS_VALIDATION_VERSION
    assert report.evaluated_count == 0
    assert report.verdict == VERDICT_INSUFFICIENT_EVIDENCE


def test_window_only_includes_predictions_inside_its_bounds(session):
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"EARLY{i}", source=SOURCE_CHATGPT, as_of=EARLY, win=True)
    for i in range(5):
        _make_evaluated(session, f"LATE{i}", source=SOURCE_CHATGPT, as_of=LATE, win=False)

    window = EvaluationWindow(label="early", start=EARLY - timedelta(days=1), end=EARLY + timedelta(days=60))
    report = compute_out_of_sample_report(session, window)

    assert report.evaluated_count == MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert report.success_rate == Decimal("1")
    assert report.verdict == VERDICT_VALIDATED


def test_discovery_source_breakdown_segments_correctly(session):
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"CHAT{i}", source=SOURCE_CHATGPT, as_of=EARLY, win=True)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"WATCH{i}", source=SOURCE_WATCHLIST, as_of=EARLY, win=False)

    window = EvaluationWindow(label="mixed", start=EARLY - timedelta(days=1), end=EARLY + timedelta(days=1))
    report = compute_out_of_sample_report(session, window)

    chat = next(m for m in report.by_discovery_source if m.source == SOURCE_CHATGPT)
    watch = next(m for m in report.by_discovery_source if m.source == SOURCE_WATCHLIST)
    assert chat.success_rate == Decimal("1")
    assert watch.success_rate == Decimal("0")


def test_overlapping_windows_are_rejected(session):
    baseline = EvaluationWindow(label="baseline", start=EARLY, end=LATE)
    candidate = EvaluationWindow(label="candidate", start=LATE - timedelta(days=1), end=LATE + timedelta(days=30))

    with pytest.raises(OverlappingEvaluationWindowsError):
        compare_out_of_sample_windows(session, baseline=baseline, candidate=candidate)


def test_comparison_with_insufficient_baseline_evidence_is_insufficient(session):
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"C{i}", source=SOURCE_CHATGPT, as_of=LATE, win=True)

    baseline = EvaluationWindow(label="baseline", start=EARLY - timedelta(days=1), end=EARLY + timedelta(days=1))
    candidate = EvaluationWindow(label="candidate", start=LATE - timedelta(days=1), end=LATE + timedelta(days=1))

    result = compare_out_of_sample_windows(session, baseline=baseline, candidate=candidate)

    assert result.verdict == VERDICT_INSUFFICIENT_EVIDENCE
    assert result.success_rate_delta is None


def test_regressed_candidate_is_flagged(session):
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"B{i}", source=SOURCE_CHATGPT, as_of=EARLY, win=True)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"C{i}", source=SOURCE_CHATGPT, as_of=LATE, win=False)

    baseline = EvaluationWindow(label="baseline", start=EARLY - timedelta(days=1), end=EARLY + timedelta(days=1))
    candidate = EvaluationWindow(label="candidate", start=LATE - timedelta(days=1), end=LATE + timedelta(days=1))

    result = compare_out_of_sample_windows(session, baseline=baseline, candidate=candidate)

    assert result.success_rate_delta == Decimal("-1")
    assert result.success_rate_delta <= -REGRESSION_MARGIN
    assert result.verdict == VERDICT_REGRESSED


def test_comparable_candidate_is_validated(session):
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"B{i}", source=SOURCE_CHATGPT, as_of=EARLY, win=(i % 2 == 0))
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"C{i}", source=SOURCE_CHATGPT, as_of=LATE, win=(i % 2 == 0))

    baseline = EvaluationWindow(label="baseline", start=EARLY - timedelta(days=1), end=EARLY + timedelta(days=1))
    candidate = EvaluationWindow(label="candidate", start=LATE - timedelta(days=1), end=LATE + timedelta(days=1))

    result = compare_out_of_sample_windows(session, baseline=baseline, candidate=candidate)

    assert result.success_rate_delta == Decimal("0")
    assert result.verdict == VERDICT_VALIDATED
