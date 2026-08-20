from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.candidate_model_comparison import (
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    VERDICT_INSUFFICIENT_EVIDENCE,
    VERDICT_REGRESSED,
    VERDICT_VALIDATED,
    compare_candidate_model,
    production_model,
)
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.discovery_segmentation import record_segment_for_discovery
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcome_measurement import OUTCOME_SUCCESS, measure_outcome
from app.outcomes import evaluate_recommendation

AS_OF = datetime(2026, 4, 10, tzinfo=timezone.utc)
DATASET_VERSION = "TEST-CMC-001"


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
    scan = DailyCandidateScan(scan_date=date(2026, 4, 10), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_completed(session, scan, symbol, *, win: bool, predicted_probability=Decimal("0.72")):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector="Energy", market_cap=Decimal("30000"))
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=predicted_probability, confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
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
    record_segment_for_discovery(session, discovery, stock, candidate)
    prediction = session.get(Prediction, generation.prediction_id)

    close = Decimal("106") if win else Decimal("95")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    outcome = evaluate_recommendation(session, prediction)
    measure_outcome(session, outcome, measured_at=AS_OF)
    return prediction


def _seed(session, *, count, win_ratio_numerator, win_ratio_denominator, prefix, predicted_probability=Decimal("0.72")):
    scan = _make_scan(session)
    for i in range(count):
        win = (i * win_ratio_denominator) < (win_ratio_numerator * count)
        _make_completed(session, scan, f"{prefix}{i}", win=win, predicted_probability=predicted_probability)
    return scan


def test_insufficient_evidence_reported_for_small_dataset(session):
    _seed(session, count=1, win_ratio_numerator=1, win_ratio_denominator=1, prefix="S")

    def candidate(record):
        return record.predicted_probability

    report = compare_candidate_model(session, dataset_version=DATASET_VERSION, candidate_model=candidate)

    assert report.verdict == VERDICT_INSUFFICIENT_EVIDENCE
    assert report.calibration_error_delta is None


def test_identical_candidate_matches_production_exactly(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed(session, count=total, win_ratio_numerator=1, win_ratio_denominator=2, prefix="S")

    report = compare_candidate_model(session, dataset_version=DATASET_VERSION, candidate_model=production_model)

    assert report.production.evaluated_count == total
    assert report.candidate.evaluated_count == total
    assert report.calibration_error_delta == Decimal("0")
    assert report.verdict == VERDICT_VALIDATED


def test_worse_candidate_is_flagged_regressed(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    # production predicts a constant 0.72 against a 50% actual win rate
    # (MAE 0.5); this candidate predicts the *opposite* of what happened,
    # which is unambiguously worse (MAE ~0.99) -- on purpose.
    _seed(session, count=total, win_ratio_numerator=1, win_ratio_denominator=2, prefix="S")

    def bad_candidate(record):
        return Decimal("0.01") if record.outcome_classification == OUTCOME_SUCCESS else Decimal("0.99")

    report = compare_candidate_model(session, dataset_version=DATASET_VERSION, candidate_model=bad_candidate)

    assert report.verdict == VERDICT_REGRESSED
    assert report.calibration_error_delta > 0


def test_better_candidate_is_validated(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    scan = _make_scan(session)
    predictions = []
    for i in range(total):
        win = i % 2 == 0
        predictions.append(_make_completed(session, scan, f"S{i}", win=win, predicted_probability=Decimal("0.72")))

    win_by_prediction = {p.id: (i % 2 == 0) for i, p in enumerate(predictions)}

    def perfect_candidate(record):
        return Decimal("0.99") if win_by_prediction[record.prediction_id] else Decimal("0.01")

    report = compare_candidate_model(session, dataset_version=DATASET_VERSION, candidate_model=perfect_candidate)

    assert report.candidate.mean_absolute_calibration_error < report.production.mean_absolute_calibration_error
    assert report.verdict == VERDICT_VALIDATED


def test_segments_and_horizon_are_populated_identically_for_both_models(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed(session, count=total, win_ratio_numerator=1, win_ratio_denominator=2, prefix="S")

    report = compare_candidate_model(session, dataset_version=DATASET_VERSION, candidate_model=production_model)

    assert len(report.production.by_horizon) == len(report.candidate.by_horizon)
    horizon_1 = next(m for m in report.production.by_horizon if m.key == "1")
    assert horizon_1.evaluated_count == total
    sector_metric = next(m for m in report.production.by_sector if m.key == "Energy")
    assert sector_metric.evaluated_count == total
    regime_metric = report.production.by_regime
    assert len(regime_metric) == 1  # full coverage -- every record gets a regime


def test_no_write_path_exists_for_promotion(session):
    total = 2 * MIN_SAMPLE_SIZE_FOR_COMPARISON
    _seed(session, count=total, win_ratio_numerator=1, win_ratio_denominator=2, prefix="S")
    before = [p.predicted_probability for p in session.query(Prediction).all()]

    compare_candidate_model(session, dataset_version=DATASET_VERSION, candidate_model=lambda r: Decimal("0.5"))

    after = [p.predicted_probability for p in session.query(Prediction).all()]
    assert before == after
