from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.confidence_analysis import (
    CALIBRATION_ERROR_MARGIN,
    CONFIDENCE_ANALYSIS_VERSION,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_OVERCONFIDENT,
    VERDICT_UNDERCONFIDENT,
    VERDICT_WELL_CALIBRATED,
    compute_confidence_analysis_report,
)
from app.db import Base
from app.models import MarketPrice, Stock
from app.outcomes import evaluate_recommendation
from app.recommendations import record_recommendation

AS_OF = datetime(2026, 8, 10, tzinfo=timezone.utc)
MIN_SAMPLE = 20  # mirrors app.trust_report.MIN_SAMPLE_SIZE_FOR_COMPARISON


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


def make_stock(session, symbol):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def make_prices(session, stock_id, closes, *, start=AS_OF):
    for offset, close in enumerate(closes, start=1):
        close = Decimal(str(close))
        session.add(MarketPrice(
            stock_id=stock_id,
            timestamp=start + timedelta(days=offset),
            open=close,
            high=close + Decimal("1"),
            low=close - Decimal("1"),
            close=close,
            volume=1000,
            source="test",
        ))
    session.flush()


def make_recommendation(session, stock, *, horizon_days=1, predicted_probability):
    return record_recommendation(
        session,
        stock_id=stock.id,
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        horizon_days=horizon_days,
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
        predicted_probability=Decimal(predicted_probability),
        confidence=Decimal("0.80"),
        model_version="m1-baseline-1",
        feature_version="f1",
        consensus_contract_version="PCC-001",
        horizon_selection_version="PHS-001",
        scoring_contract_version="POS-001",
        opportunity_score=Decimal("70.00"),
    )


def _make_evaluated(session, symbol, *, horizon_days=1, predicted_probability, win: bool):
    stock = make_stock(session, symbol)
    rec = make_recommendation(session, stock, horizon_days=horizon_days, predicted_probability=predicted_probability)
    filler = [100] * (horizon_days - 1)
    closes = filler + ([106] if win else [95])
    make_prices(session, stock.id, closes)
    return evaluate_recommendation(session, rec)


def test_empty_history_reports_insufficient_sample_everywhere(session):
    report = compute_confidence_analysis_report(session)

    assert report.report_version == CONFIDENCE_ANALYSIS_VERSION
    assert report.evaluated_count == 0
    assert all(b.verdict == VERDICT_INSUFFICIENT_SAMPLE for b in report.overall_buckets)


def test_well_calibrated_bucket_shows_zero_error(session):
    # predicted_probability=0.75 for all; exactly 75% (15/20) succeed
    for i in range(MIN_SAMPLE):
        _make_evaluated(session, f"S{i}", predicted_probability="0.75", win=(i < 15))

    report = compute_confidence_analysis_report(session)
    bucket = next(b for b in report.overall_buckets if b.lower == Decimal("0.7"))

    assert bucket.evaluated_count == MIN_SAMPLE
    assert bucket.average_predicted_probability == Decimal("0.75")
    assert bucket.observed_success_rate == Decimal("15") / Decimal("20")
    assert bucket.calibration_error == Decimal("0")
    assert bucket.verdict == VERDICT_WELL_CALIBRATED


def test_overconfident_bucket_is_flagged(session):
    # predicted_probability=0.95 but only 20% (4/20) actually succeed
    for i in range(MIN_SAMPLE):
        _make_evaluated(session, f"S{i}", predicted_probability="0.95", win=(i < 4))

    report = compute_confidence_analysis_report(session)
    bucket = next(b for b in report.overall_buckets if b.lower == Decimal("0.9"))

    assert bucket.calibration_error >= CALIBRATION_ERROR_MARGIN
    assert bucket.verdict == VERDICT_OVERCONFIDENT


def test_underconfident_bucket_is_flagged(session):
    # predicted_probability=0.65 but 95% (19/20) actually succeed
    for i in range(MIN_SAMPLE):
        _make_evaluated(session, f"S{i}", predicted_probability="0.65", win=(i < 19))

    report = compute_confidence_analysis_report(session)
    bucket = next(b for b in report.overall_buckets if b.lower == Decimal("0.6"))

    assert bucket.calibration_error <= -CALIBRATION_ERROR_MARGIN
    assert bucket.verdict == VERDICT_UNDERCONFIDENT


def test_gap_below_minimum_sample_is_insufficient_not_flagged(session):
    # same large gap as the overconfident case, but only 5 samples
    for i in range(5):
        _make_evaluated(session, f"S{i}", predicted_probability="0.95", win=False)

    report = compute_confidence_analysis_report(session)
    bucket = next(b for b in report.overall_buckets if b.lower == Decimal("0.9"))

    assert bucket.evaluated_count < MIN_SAMPLE
    assert bucket.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_by_horizon_breakdown_is_always_present_for_all_supported_horizons(session):
    for i in range(MIN_SAMPLE):
        _make_evaluated(session, f"S{i}", horizon_days=1, predicted_probability="0.75", win=(i < 15))

    report = compute_confidence_analysis_report(session)

    assert {h.horizon_days for h in report.by_horizon} == {1, 3, 5, 7}
    horizon_1 = next(h for h in report.by_horizon if h.horizon_days == 1)
    bucket = next(b for b in horizon_1.buckets if b.lower == Decimal("0.7"))
    assert bucket.evaluated_count == MIN_SAMPLE
