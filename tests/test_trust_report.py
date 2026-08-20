from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MarketPrice, Stock
from app.outcomes import evaluate_recommendation
from app.recommendations import record_recommendation
from app.trust_report import (
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    TRUST_REPORT_VERSION,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_OK,
    VERDICT_WEAK,
    compute_trust_report,
)

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


def make_stock(session, symbol):
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, created_at=now, updated_at=now)
    session.add(stock)
    session.flush()
    return stock


def make_prices(session, stock_id, closes, *, start=AS_OF, valid=True):
    for offset, close in enumerate(closes, start=1):
        close = Decimal(str(close))
        session.add(MarketPrice(
            stock_id=stock_id,
            timestamp=start + timedelta(days=offset),
            open=close if valid else Decimal("0"),
            high=close + Decimal("1") if valid else Decimal("-5"),
            low=close - Decimal("1") if valid else Decimal("999"),
            close=close,
            volume=1000 if valid else 0,
            source="test",
        ))
    session.flush()


def make_recommendation(session, stock, *, horizon_days=3, predicted_probability="0.70", target_return="0.05", stop_return="-0.03"):
    return record_recommendation(
        session,
        stock_id=stock.id,
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        horizon_days=horizon_days,
        target_return=Decimal(target_return),
        stop_return=Decimal(stop_return),
        predicted_probability=Decimal(predicted_probability),
        confidence=Decimal("0.80"),
        model_version="m1-baseline-1",
        feature_version="f1",
        consensus_contract_version="PCC-001",
        horizon_selection_version="PHS-001",
        scoring_contract_version="POS-001",
        opportunity_score=Decimal("70.00"),
    )


def _make_evaluated(session, symbol, *, horizon_days, predicted_probability, win: bool):
    """Builds a recommendation that resolves deterministically at exactly the given
    horizon regardless of its length: every day before the last is a flat 100 close
    (never touches the +5%/-3% thresholds), and the final day either hits the target
    (close 106, high 107 >= 105) or the stop (close 95, low 94 <= 97)."""
    stock = make_stock(session, symbol)
    rec = make_recommendation(session, stock, horizon_days=horizon_days, predicted_probability=predicted_probability)
    filler = [100] * (horizon_days - 1)
    closes = filler + ([106] if win else [95])
    make_prices(session, stock.id, closes)
    return evaluate_recommendation(session, rec)


def test_empty_history_reports_insufficient_sample_everywhere(session):
    report = compute_trust_report(session)

    assert report.report_version == TRUST_REPORT_VERSION
    assert report.performance.total_recommendations == 0
    assert all(h.verdict == VERDICT_INSUFFICIENT_SAMPLE for h in report.horizon_trust)
    assert all(b.verdict == VERDICT_INSUFFICIENT_SAMPLE for b in report.probability_bucket_trust)


def test_wraps_m16_performance_data_unchanged(session):
    for i in range(3):
        _make_evaluated(session, f"WIN{i}", horizon_days=3, predicted_probability="0.70", win=True)
    for i in range(2):
        _make_evaluated(session, f"LOSE{i}", horizon_days=3, predicted_probability="0.70", win=False)

    report = compute_trust_report(session)

    assert report.performance.evaluated_count == 5
    assert report.performance.success_count == 3
    assert report.performance.failure_count == 2
    assert report.performance.overall_success_rate == Decimal("3") / Decimal("5")


def test_horizon_below_minimum_sample_is_insufficient_not_weak(session):
    # only 5 samples at horizon 3, all failing -- far below MIN_SAMPLE_SIZE_FOR_COMPARISON
    for i in range(5):
        _make_evaluated(session, f"S{i}", horizon_days=3, predicted_probability="0.70", win=False)

    report = compute_trust_report(session)
    horizon_3 = next(h for h in report.horizon_trust if h.horizon.horizon_days == 3)

    assert horizon_3.horizon.evaluated_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert horizon_3.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_horizon_with_enough_samples_and_poor_rate_is_flagged_weak(session):
    # horizon 1: enough samples, all fail -> 0% success, far below overall
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"H1_{i}", horizon_days=1, predicted_probability="0.70", win=False)
    # horizon 3: enough samples, all succeed -> pulls the overall rate up
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"H3_{i}", horizon_days=3, predicted_probability="0.70", win=True)

    report = compute_trust_report(session)
    horizon_1 = next(h for h in report.horizon_trust if h.horizon.horizon_days == 1)
    horizon_3 = next(h for h in report.horizon_trust if h.horizon.horizon_days == 3)

    assert report.performance.overall_success_rate == Decimal("0.5")
    assert horizon_1.horizon.success_rate == Decimal("0")
    assert horizon_1.verdict == VERDICT_WEAK
    assert horizon_3.horizon.success_rate == Decimal("1")
    assert horizon_3.verdict == VERDICT_OK


def test_horizon_matching_overall_rate_with_enough_samples_is_ok(session):
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"S{i}", horizon_days=1, predicted_probability="0.70", win=(i % 2 == 0))

    report = compute_trust_report(session)
    horizon_1 = next(h for h in report.horizon_trust if h.horizon.horizon_days == 1)

    assert horizon_1.horizon.evaluated_count == MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert horizon_1.verdict == VERDICT_OK


def test_probability_bucket_weakness_is_flagged_like_horizons(session):
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"LOW{i}", horizon_days=1, predicted_probability="0.05", win=False)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"HIGH{i}", horizon_days=1, predicted_probability="0.95", win=True)

    report = compute_trust_report(session)
    low_bucket = next(b for b in report.probability_bucket_trust if b.bucket.lower == Decimal("0.0"))
    high_bucket = next(b for b in report.probability_bucket_trust if b.bucket.lower == Decimal("0.9"))
    empty_buckets = [
        b for b in report.probability_bucket_trust if b.bucket.lower not in (Decimal("0.0"), Decimal("0.9"))
    ]

    assert report.performance.overall_success_rate == Decimal("0.5")
    assert low_bucket.verdict == VERDICT_WEAK
    assert high_bucket.verdict == VERDICT_OK
    assert all(b.verdict == VERDICT_INSUFFICIENT_SAMPLE for b in empty_buckets)


def test_failures_and_unevaluable_remain_visible_in_the_underlying_performance(session):
    fail_stock = make_stock(session, "FAIL")
    fail_rec = make_recommendation(session, fail_stock, horizon_days=3)
    make_prices(session, fail_stock.id, [99, 95, 98])
    evaluate_recommendation(session, fail_rec)

    unevaluable_stock = make_stock(session, "BAD")
    unevaluable_rec = make_recommendation(session, unevaluable_stock, horizon_days=3)
    make_prices(session, unevaluable_stock.id, [100, 101, 102], valid=False)
    evaluate_recommendation(session, unevaluable_rec)

    report = compute_trust_report(session)

    assert report.performance.failure_count == 1
    assert report.performance.unevaluable_count == 1
