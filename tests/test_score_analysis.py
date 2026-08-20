from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MarketPrice, Stock
from app.outcomes import evaluate_recommendation
from app.recommendations import record_recommendation
from app.score_analysis import (
    MIN_SAMPLE_SIZE_FOR_COMPARISON,
    SCORE_ANALYSIS_VERSION,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_OK,
    VERDICT_WEAK,
    compute_score_analysis_report,
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
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
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


def make_recommendation(session, stock, *, horizon_days=3, opportunity_score, target_return="0.05", stop_return="-0.03"):
    return record_recommendation(
        session,
        stock_id=stock.id,
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        horizon_days=horizon_days,
        target_return=Decimal(target_return),
        stop_return=Decimal(stop_return),
        predicted_probability=Decimal("0.70"),
        confidence=Decimal("0.80"),
        model_version="m1-baseline-1",
        feature_version="f1",
        consensus_contract_version="PCC-001",
        horizon_selection_version="PHS-001",
        scoring_contract_version="POS-001",
        opportunity_score=Decimal(opportunity_score),
    )


def _make_evaluated(session, symbol, *, horizon_days, opportunity_score, win: bool):
    stock = make_stock(session, symbol)
    rec = make_recommendation(session, stock, horizon_days=horizon_days, opportunity_score=opportunity_score)
    filler = [100] * (horizon_days - 1)
    closes = filler + ([106] if win else [95])
    make_prices(session, stock.id, closes)
    return evaluate_recommendation(session, rec)


def test_empty_history_reports_insufficient_sample_everywhere(session):
    report = compute_score_analysis_report(session)

    assert report.report_version == SCORE_ANALYSIS_VERSION
    assert report.total_recommendations == 0
    assert report.overall_success_rate is None
    assert all(b.verdict == VERDICT_INSUFFICIENT_SAMPLE for b in report.overall_bands)
    for horizon in report.by_horizon:
        assert all(b.verdict == VERDICT_INSUFFICIENT_SAMPLE for b in horizon.bands)


def test_open_and_unevaluable_are_counted_but_excluded_from_success_rate(session):
    success_stock = make_stock(session, "AAA")
    success_rec = make_recommendation(session, success_stock, horizon_days=3, opportunity_score="70.00")
    make_prices(session, success_stock.id, [101, 106, 103])
    evaluate_recommendation(session, success_rec)

    unevaluable_stock = make_stock(session, "BBB")
    unevaluable_rec = make_recommendation(session, unevaluable_stock, horizon_days=3, opportunity_score="70.00")
    make_prices(session, unevaluable_stock.id, [100, 101, 102], valid=False)
    evaluate_recommendation(session, unevaluable_rec)

    open_stock = make_stock(session, "CCC")
    make_recommendation(session, open_stock, horizon_days=5, opportunity_score="70.00")

    report = compute_score_analysis_report(session)

    assert report.total_recommendations == 3
    assert report.open_count == 1
    assert report.unevaluable_count == 1
    assert report.evaluated_count == 1
    assert report.overall_success_rate == Decimal("1")


def test_score_band_boundaries_are_exact(session):
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"S{i}", horizon_days=1, opportunity_score="50.00", win=(i % 2 == 0))

    report = compute_score_analysis_report(session)
    band_50 = next(b for b in report.overall_bands if b.band.lower == Decimal("50"))
    band_40 = next(b for b in report.overall_bands if b.band.lower == Decimal("40"))

    assert band_50.band.evaluated_count == MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert band_40.band.evaluated_count == 0


def test_band_below_minimum_sample_is_insufficient_not_weak(session):
    for i in range(5):
        _make_evaluated(session, f"S{i}", horizon_days=1, opportunity_score="20.00", win=False)

    report = compute_score_analysis_report(session)
    band_20 = next(b for b in report.overall_bands if b.band.lower == Decimal("20"))

    assert band_20.band.evaluated_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
    assert band_20.verdict == VERDICT_INSUFFICIENT_SAMPLE


def test_weak_band_is_flagged_relative_to_overall_rate(session):
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"LOW{i}", horizon_days=1, opportunity_score="10.00", win=False)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"HIGH{i}", horizon_days=1, opportunity_score="90.00", win=True)

    report = compute_score_analysis_report(session)
    low_band = next(b for b in report.overall_bands if b.band.lower == Decimal("10"))
    high_band = next(b for b in report.overall_bands if b.band.lower == Decimal("90"))

    assert report.overall_success_rate == Decimal("0.5")
    assert low_band.verdict == VERDICT_WEAK
    assert high_band.verdict == VERDICT_OK


def test_by_horizon_breakdown_segments_bands_per_horizon(session):
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"H1_{i}", horizon_days=1, opportunity_score="80.00", win=True)
    for i in range(MIN_SAMPLE_SIZE_FOR_COMPARISON):
        _make_evaluated(session, f"H3_{i}", horizon_days=3, opportunity_score="80.00", win=False)

    report = compute_score_analysis_report(session)
    horizon_1 = next(h for h in report.by_horizon if h.horizon_days == 1)
    horizon_3 = next(h for h in report.by_horizon if h.horizon_days == 3)
    band_80_h1 = next(b for b in horizon_1.bands if b.band.lower == Decimal("80"))
    band_80_h3 = next(b for b in horizon_3.bands if b.band.lower == Decimal("80"))

    assert band_80_h1.band.success_rate == Decimal("1")
    assert band_80_h3.band.success_rate == Decimal("0")
    # every supported horizon is always present, even with zero samples
    assert {h.horizon_days for h in report.by_horizon} == {1, 3, 5, 7}
