from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.candidate_model_evaluation import (
    CANDIDATE_MODEL_EVALUATION_VERSION,
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    VERDICT_INSUFFICIENT_EVIDENCE,
    VERDICT_REGRESSED,
    VERDICT_VALIDATED,
    compare_candidate_model,
    compute_window_evaluation,
)
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.discovery_segmentation import record_segment_for_discovery
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


def _make_evaluated(session, scan, symbol, *, as_of, win: bool, sector="Energy", market_cap=Decimal("30000")):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector=sector, market_cap=market_cap)
    session.add(stock)
    session.flush()
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
        session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="test", discovered_at=as_of
    )
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    record_segment_for_discovery(session, discovery, stock, candidate)
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


BASELINE_AS_OF = datetime(2026, 1, 10, tzinfo=timezone.utc)
CANDIDATE_AS_OF = datetime(2026, 6, 10, tzinfo=timezone.utc)
BASELINE_WINDOW = EvaluationWindow(label="baseline", start=datetime(2026, 1, 1, tzinfo=timezone.utc), end=datetime(2026, 1, 31, tzinfo=timezone.utc))
CANDIDATE_WINDOW = EvaluationWindow(label="candidate", start=datetime(2026, 6, 1, tzinfo=timezone.utc), end=datetime(2026, 6, 30, tzinfo=timezone.utc))


def test_window_evaluation_reports_returns_and_calibration(session):
    scan = _make_scan(session, BASELINE_AS_OF.date())
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, scan, f"S{i}", as_of=BASELINE_AS_OF, win=(i % 2 == 0))

    report = compute_window_evaluation(session, BASELINE_WINDOW)

    assert report.version == CANDIDATE_MODEL_EVALUATION_VERSION
    assert report.evaluated_count == MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert report.success_rate == Decimal("0.5")
    assert report.average_actual_return is not None
    assert report.average_predicted_return == Decimal("0.05")
    assert report.mean_absolute_calibration_error is not None
    assert "overall" not in report.insufficient_sample_dimensions


def test_horizon_breakdown_always_includes_all_supported_horizons(session):
    scan = _make_scan(session, BASELINE_AS_OF.date())
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, scan, f"S{i}", as_of=BASELINE_AS_OF, win=True)

    report = compute_window_evaluation(session, BASELINE_WINDOW)

    assert {m.key for m in report.by_horizon} == {"1", "3", "5", "7"}
    horizon_1 = next(m for m in report.by_horizon if m.key == "1")
    assert horizon_1.evaluated_count == MIN_SAMPLE_SIZE_FOR_COMPARISON


def test_sector_market_cap_source_and_regime_segmentation(session):
    scan = _make_scan(session, BASELINE_AS_OF.date())
    for i in range(6):
        _make_evaluated(session, scan, f"S{i}", as_of=BASELINE_AS_OF, win=True, sector="Energy", market_cap=Decimal("30000"))
    classify_market_regime(session, scan.id)

    report = compute_window_evaluation(session, BASELINE_WINDOW)

    sector_metric = next(m for m in report.by_sector if m.key == "Energy")
    cap_metric = next(m for m in report.by_market_cap_bucket if m.key == "LARGE_CAP")
    source_metric = next(m for m in report.by_discovery_source if m.key == SOURCE_CHATGPT)
    regime_metrics = report.by_regime

    assert sector_metric.evaluated_count == 6
    assert cap_metric.evaluated_count == 6
    assert source_metric.evaluated_count == 6
    assert len(regime_metrics) == 1
    assert regime_metrics[0].evaluated_count == 6


def test_insufficient_sample_dimensions_are_disclosed(session):
    scan = _make_scan(session, BASELINE_AS_OF.date())
    for i in range(5):
        _make_evaluated(session, scan, f"S{i}", as_of=BASELINE_AS_OF, win=True, sector="Energy")

    report = compute_window_evaluation(session, BASELINE_WINDOW)

    assert "overall" in report.insufficient_sample_dimensions
    assert "sector:Energy" in report.insufficient_sample_dimensions


def test_overlapping_windows_are_rejected(session):
    overlapping_candidate = EvaluationWindow(
        label="candidate", start=BASELINE_WINDOW.end - timedelta(days=1), end=BASELINE_WINDOW.end + timedelta(days=30)
    )

    with pytest.raises(OverlappingEvaluationWindowsError):
        compare_candidate_model(session, baseline=BASELINE_WINDOW, candidate=overlapping_candidate)


def test_comparison_with_insufficient_evidence(session):
    scan = _make_scan(session, CANDIDATE_AS_OF.date())
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, scan, f"S{i}", as_of=CANDIDATE_AS_OF, win=True)

    result = compare_candidate_model(session, baseline=BASELINE_WINDOW, candidate=CANDIDATE_WINDOW)

    assert result.verdict == VERDICT_INSUFFICIENT_EVIDENCE
    assert result.success_rate_delta is None


def test_regressed_candidate_is_flagged(session):
    baseline_scan = _make_scan(session, BASELINE_AS_OF.date())
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, baseline_scan, f"B{i}", as_of=BASELINE_AS_OF, win=True)
    candidate_scan = _make_scan(session, CANDIDATE_AS_OF.date())
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, candidate_scan, f"C{i}", as_of=CANDIDATE_AS_OF, win=False)

    result = compare_candidate_model(session, baseline=BASELINE_WINDOW, candidate=CANDIDATE_WINDOW)

    assert result.success_rate_delta == Decimal("-1")
    assert result.verdict == VERDICT_REGRESSED


def test_comparable_candidate_is_validated(session):
    baseline_scan = _make_scan(session, BASELINE_AS_OF.date())
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, baseline_scan, f"B{i}", as_of=BASELINE_AS_OF, win=(i % 2 == 0))
    candidate_scan = _make_scan(session, CANDIDATE_AS_OF.date())
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, candidate_scan, f"C{i}", as_of=CANDIDATE_AS_OF, win=(i % 2 == 0))

    result = compare_candidate_model(session, baseline=BASELINE_WINDOW, candidate=CANDIDATE_WINDOW)

    assert result.success_rate_delta == Decimal("0")
    assert result.verdict == VERDICT_VALIDATED
