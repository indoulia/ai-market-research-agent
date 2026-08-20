from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.calibration import (
    CALIBRATION_VERSION,
    INSUFFICIENT_SAMPLE,
    MATERIAL_ERROR_THRESHOLD,
    MIN_SAMPLE_SIZE,
    OVERCONFIDENT,
    UNDERCONFIDENT,
    WELL_CALIBRATED,
    compute_calibration_report,
)
from app.db import Base
from app.models import MarketPrice, Stock
from app.outcomes import evaluate_recommendation
from app.recommendations import record_recommendation

AS_OF = datetime(2026, 8, 10, tzinfo=timezone.utc)


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


_counter = 0


def make_evaluated(session, predicted_probability, want_success, horizon_days=1):
    global _counter
    _counter += 1
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    stock = Stock(symbol=f"S{_counter:05d}", exchange="NSE", is_active=True, created_at=now, updated_at=now)
    session.add(stock)
    session.flush()

    rec = record_recommendation(
        session,
        stock_id=stock.id,
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        horizon_days=horizon_days,
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
        predicted_probability=predicted_probability,
        confidence=Decimal("0.80"),
        model_version="m1-baseline-1",
        feature_version="f1",
    )
    close = Decimal("106") if want_success else Decimal("95")  # day 1 always resolves the outcome
    for offset in range(1, horizon_days + 1):
        session.add(MarketPrice(
            stock_id=stock.id, timestamp=AS_OF + timedelta(days=offset),
            open=close, high=close + 1, low=close - 1, close=close, volume=1000, source="test",
        ))
    session.flush()
    evaluate_recommendation(session, rec)
    return rec


def make_open(session, predicted_probability, horizon_days=5):
    global _counter
    _counter += 1
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    stock = Stock(symbol=f"S{_counter:05d}", exchange="NSE", is_active=True, created_at=now, updated_at=now)
    session.add(stock)
    session.flush()
    return record_recommendation(
        session, stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        horizon_days=horizon_days, target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
        predicted_probability=predicted_probability, confidence=Decimal("0.80"),
        model_version="m1-baseline-1", feature_version="f1",
    )


def make_unevaluable(session, predicted_probability, horizon_days=1):
    global _counter
    _counter += 1
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    stock = Stock(symbol=f"S{_counter:05d}", exchange="NSE", is_active=True, created_at=now, updated_at=now)
    session.add(stock)
    session.flush()
    rec = record_recommendation(
        session, stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        horizon_days=horizon_days, target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
        predicted_probability=predicted_probability, confidence=Decimal("0.80"),
        model_version="m1-baseline-1", feature_version="f1",
    )
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("0"), high=Decimal("-5"), low=Decimal("999"), close=Decimal("100"),
        volume=0, source="test",
    ))
    session.flush()
    return evaluate_recommendation(session, rec)


def _bucket_at(report_buckets, lower):
    return next(b for b in report_buckets if b.lower == lower)


def test_bucket_with_insufficient_sample_is_marked_explicitly_not_as_reliable(session):
    for _ in range(5):
        make_evaluated(session, Decimal("0.75"), want_success=True)

    report = compute_calibration_report(session)
    bucket = _bucket_at(report.overall, Decimal("0.7"))

    assert bucket.sample_size == 5
    assert bucket.sample_size < MIN_SAMPLE_SIZE
    assert bucket.assessment == INSUFFICIENT_SAMPLE
    assert bucket.calibration_error is None
    # predicted/observed are still shown alongside the explicit sample size
    assert bucket.predicted_probability == Decimal("0.75")
    assert bucket.observed_success_rate == Decimal("1")


def test_well_calibrated_bucket_when_observed_matches_predicted(session):
    for _ in range(28):
        make_evaluated(session, Decimal("0.70"), want_success=True)
    for _ in range(12):
        make_evaluated(session, Decimal("0.70"), want_success=False)

    report = compute_calibration_report(session)
    bucket = _bucket_at(report.overall, Decimal("0.7"))

    assert bucket.sample_size == 40
    assert bucket.predicted_probability == Decimal("0.70")
    assert bucket.observed_success_rate == Decimal("0.70")
    assert bucket.calibration_error == Decimal("0")
    assert bucket.assessment == WELL_CALIBRATED


def test_overconfident_bucket_when_observed_materially_below_predicted(session):
    for _ in range(20):
        make_evaluated(session, Decimal("0.80"), want_success=True)
    for _ in range(20):
        make_evaluated(session, Decimal("0.80"), want_success=False)

    report = compute_calibration_report(session)
    bucket = _bucket_at(report.overall, Decimal("0.8"))

    assert bucket.sample_size == 40
    assert bucket.observed_success_rate == Decimal("0.50")
    assert bucket.calibration_error == Decimal("0.50") - Decimal("0.80")
    assert bucket.calibration_error <= -MATERIAL_ERROR_THRESHOLD
    assert bucket.assessment == OVERCONFIDENT


def test_underconfident_bucket_when_observed_materially_above_predicted(session):
    for _ in range(36):
        make_evaluated(session, Decimal("0.60"), want_success=True)
    for _ in range(4):
        make_evaluated(session, Decimal("0.60"), want_success=False)

    report = compute_calibration_report(session)
    bucket = _bucket_at(report.overall, Decimal("0.6"))

    assert bucket.sample_size == 40
    assert bucket.observed_success_rate == Decimal("0.90")
    assert bucket.calibration_error == Decimal("0.90") - Decimal("0.60")
    assert bucket.calibration_error >= MATERIAL_ERROR_THRESHOLD
    assert bucket.assessment == UNDERCONFIDENT


def test_only_objectively_evaluated_outcomes_feed_calibration(session):
    for _ in range(30):
        make_evaluated(session, Decimal("0.70"), want_success=True)
    make_open(session, Decimal("0.70"))
    make_unevaluable(session, Decimal("0.70"))

    report = compute_calibration_report(session)
    bucket = _bucket_at(report.overall, Decimal("0.7"))

    # open/unevaluable rows must not inflate the sample size or skew the rate
    assert bucket.sample_size == 30
    assert bucket.observed_success_rate == Decimal("1")


def test_calibration_by_horizon_is_reported_for_every_supported_horizon(session):
    for _ in range(21):
        make_evaluated(session, Decimal("0.70"), want_success=True, horizon_days=1)
    for _ in range(9):
        make_evaluated(session, Decimal("0.70"), want_success=False, horizon_days=1)
    for _ in range(5):
        make_evaluated(session, Decimal("0.70"), want_success=True, horizon_days=3)

    report = compute_calibration_report(session)
    by_horizon = {h.horizon_days: h for h in report.by_horizon}

    assert set(by_horizon) == {1, 3, 5, 7}
    horizon_1_bucket = _bucket_at(by_horizon[1].buckets, Decimal("0.7"))
    horizon_3_bucket = _bucket_at(by_horizon[3].buckets, Decimal("0.7"))
    horizon_5_bucket = _bucket_at(by_horizon[5].buckets, Decimal("0.7"))

    assert horizon_1_bucket.sample_size == 30
    assert horizon_1_bucket.assessment == WELL_CALIBRATED
    assert horizon_3_bucket.sample_size == 5
    assert horizon_3_bucket.assessment == INSUFFICIENT_SAMPLE
    # a horizon with zero evaluated recommendations is still reported, not omitted
    assert horizon_5_bucket.sample_size == 0
    assert horizon_5_bucket.assessment == INSUFFICIENT_SAMPLE
    assert horizon_5_bucket.predicted_probability is None
    assert horizon_5_bucket.observed_success_rate is None


def test_report_is_deterministic_and_repeatable(session):
    for _ in range(10):
        make_evaluated(session, Decimal("0.70"), want_success=True)

    first = compute_calibration_report(session)
    second = compute_calibration_report(session)
    assert first == second
    assert first.calibration_version == CALIBRATION_VERSION


def test_historical_predictions_are_not_modified_by_computing_the_report(session):
    rec = make_evaluated(session, Decimal("0.70"), want_success=True)
    original_probability = rec.predicted_probability

    compute_calibration_report(session)

    session.refresh(rec)
    assert rec.predicted_probability == original_probability
