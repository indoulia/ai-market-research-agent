from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MarketPrice, Stock
from app.outcomes import evaluate_recommendation
from app.performance import REPORT_VERSION, compute_performance_report
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


def make_recommendation(session, stock, *, horizon_days=5, predicted_probability="0.70", target_return="0.05", stop_return="-0.03"):
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


def test_empty_history_reports_no_data_rather_than_a_fabricated_rate(session):
    report = compute_performance_report(session)

    assert report.report_version == REPORT_VERSION
    assert report.total_recommendations == 0
    assert report.evaluated_count == 0
    assert report.overall_success_rate is None
    assert all(h.success_rate is None for h in report.by_horizon)
    assert all(b.success_rate is None for b in report.by_probability_bucket)
    assert report.returns.average_actual_return is None


def test_overall_success_rate_excludes_open_and_unevaluable_but_still_counts_them(session):
    # each recommendation gets its own stock so their evaluation windows can never overlap
    success_stock = make_stock(session, "AAA")
    success_rec = make_recommendation(session, success_stock, horizon_days=3)
    make_prices(session, success_stock.id, [101, 106, 103])  # day 2 high 107 >= target 105
    evaluate_recommendation(session, success_rec)

    failure_stock = make_stock(session, "BBB")
    failure_rec = make_recommendation(session, failure_stock, horizon_days=3)
    make_prices(session, failure_stock.id, [99, 95, 98])  # day 2 low 94 <= stop 97
    evaluate_recommendation(session, failure_rec)

    unevaluable_stock = make_stock(session, "CCC")
    unevaluable_rec = make_recommendation(session, unevaluable_stock, horizon_days=3)
    make_prices(session, unevaluable_stock.id, [100, 101, 102], valid=False)
    evaluate_recommendation(session, unevaluable_rec)

    # not enough price history yet: stays OPEN, no PredictionOutcome row at all
    open_stock = make_stock(session, "DDD")
    make_recommendation(session, open_stock, horizon_days=5)

    report = compute_performance_report(session)

    assert report.total_recommendations == 4
    assert report.open_count == 1
    assert report.unevaluable_count == 1
    assert report.evaluated_count == 2
    assert report.success_count == 1
    assert report.failure_count == 1
    assert report.overall_success_rate == Decimal("0.5")


def test_horizon_breakdown_is_reported_per_supported_horizon_with_zero_samples_shown(session):
    # each recommendation gets its own stock so their evaluation windows can never overlap
    stock1 = make_stock(session, "AAA")
    rec1 = make_recommendation(session, stock1, horizon_days=1)
    make_prices(session, stock1.id, [101])
    evaluate_recommendation(session, rec1)

    stock3 = make_stock(session, "BBB")
    rec3 = make_recommendation(session, stock3, horizon_days=3, target_return="0.05", stop_return="-0.03")
    make_prices(session, stock3.id, [99, 95, 98])
    evaluate_recommendation(session, rec3)

    report = compute_performance_report(session)
    by_horizon = {h.horizon_days: h for h in report.by_horizon}

    assert set(by_horizon) == {1, 3, 5, 7}
    assert by_horizon[1].evaluated_count == 1
    assert by_horizon[1].success_count == 1
    assert by_horizon[1].success_rate == Decimal("1")
    assert by_horizon[3].evaluated_count == 1
    assert by_horizon[3].failure_count == 1
    assert by_horizon[3].success_rate == Decimal("0")
    # never evaluated at these horizons: explicit zero, not omitted
    assert by_horizon[5].evaluated_count == 0
    assert by_horizon[5].success_rate is None
    assert by_horizon[7].evaluated_count == 0
    assert by_horizon[7].success_rate is None


def test_returns_are_computed_against_known_fixtures(session):
    # each recommendation gets its own stock so their evaluation windows can never overlap
    win_stock = make_stock(session, "AAA")
    win = make_recommendation(session, win_stock, horizon_days=3, target_return="0.05", stop_return="-0.03")
    make_prices(session, win_stock.id, [101, 106, 103])
    evaluate_recommendation(session, win)  # actual_return == 0.05 (target hit exactly)

    loss_stock = make_stock(session, "BBB")
    loss = make_recommendation(session, loss_stock, horizon_days=3, target_return="0.05", stop_return="-0.03")
    make_prices(session, loss_stock.id, [99, 95, 98])
    evaluate_recommendation(session, loss)  # actual_return == -0.03 (stop hit exactly)

    report = compute_performance_report(session)
    returns = report.returns

    assert returns.evaluated_count == 2
    assert returns.average_predicted_return == Decimal("0.05")
    assert returns.average_actual_return == (Decimal("0.05") + Decimal("-0.03")) / 2
    assert returns.winning_count == 1
    assert returns.average_winning_return == Decimal("0.05")
    assert returns.losing_count == 1
    assert returns.average_losing_return == Decimal("-0.03")


def test_probability_bucket_breakdown_places_candidates_in_the_correct_bucket(session):
    # each recommendation gets its own stock so their evaluation windows can never overlap
    low_stock = make_stock(session, "AAA")
    low_p = make_recommendation(session, low_stock, horizon_days=1, predicted_probability="0.62")
    make_prices(session, low_stock.id, [101])
    evaluate_recommendation(session, low_p)

    high_stock = make_stock(session, "BBB")
    high_p = make_recommendation(session, high_stock, horizon_days=1, predicted_probability="0.95")
    make_prices(session, high_stock.id, [101])
    evaluate_recommendation(session, high_p)

    report = compute_performance_report(session)
    low_bucket = next(b for b in report.by_probability_bucket if b.lower == Decimal("0.6"))
    high_bucket = next(b for b in report.by_probability_bucket if b.lower == Decimal("0.9"))

    assert len(report.by_probability_bucket) == 10
    assert low_bucket.evaluated_count == 1
    assert high_bucket.evaluated_count == 1
    # every other bucket explicitly present with zero samples, not omitted
    zero_buckets = [b for b in report.by_probability_bucket if b not in (low_bucket, high_bucket)]
    assert all(b.evaluated_count == 0 and b.success_rate is None for b in zero_buckets)


def test_failed_recommendations_remain_visible_not_cherry_picked(session):
    # each recommendation gets its own stock so their evaluation windows can never overlap
    for i, symbol in enumerate(["BBB", "CCC", "DDD"]):
        stock = make_stock(session, symbol)
        rec = make_recommendation(session, stock, horizon_days=3, target_return="0.05", stop_return="-0.03")
        make_prices(session, stock.id, [99, 95, 98])
        evaluate_recommendation(session, rec)

    report = compute_performance_report(session)

    assert report.failure_count == 3
    assert report.success_count == 0
    assert report.overall_success_rate == Decimal("0")
