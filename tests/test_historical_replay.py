from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.historical_replay import (
    LIMITATION_NO_HISTORICAL_DATA,
    LIMITATION_PREFIX_EXCLUDED_AT_REPLAY,
    REPLAY_RULE_VERSION,
    replay_generation,
)
from app.market_data.quality import NSE_TIMEZONE
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.recommendation_generator import generate_recommendation_for_candidate
from app.scan import CandidateSignals, run_daily_candidate_scan

SCAN_DATE = date(2026, 8, 21)
AS_OF = datetime(2026, 8, 21, tzinfo=timezone.utc)
REPLAYED_AT = datetime(2026, 9, 1, tzinfo=timezone.utc)


class StubSignalProvider:
    model_version = "test-model-1"

    def __init__(self, predicted_probability=Decimal("0.65"), confidence=Decimal("0.70")):
        self._predicted_probability = predicted_probability
        self._confidence = confidence

    def predict(self, stock_id, features):
        return CandidateSignals(predicted_probability=self._predicted_probability, confidence=self._confidence)


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


def _make_stock(session, symbol="RELIANCE"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _make_rising_price_history(session, stock_id, last_session=SCAN_DATE, count=25, base_price=Decimal("100")):
    for offset in range(count):
        session_date = last_session - timedelta(days=count - 1 - offset)
        timestamp = datetime.combine(session_date, time.min, NSE_TIMEZONE)
        price = base_price + Decimal(offset)
        session.add(
            MarketPrice(
                stock_id=stock_id,
                timestamp=timestamp,
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price,
                volume=10_000,
                source="test",
            )
        )
    session.flush()


def _original_generation(session, signal_provider):
    stock = _make_stock(session)
    _make_rising_price_history(session, stock.id)
    summary = run_daily_candidate_scan(session, SCAN_DATE, signal_provider)
    candidate = summary.candidates[0]
    generation = generate_recommendation_for_candidate(
        session,
        candidate,
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )
    return stock, generation


def test_qualifying_replay_matches_the_original_decision(session):
    stock, generation = _original_generation(session, StubSignalProvider())

    run = replay_generation(session, generation, StubSignalProvider(), replayed_at=REPLAYED_AT)

    assert run.matches_original is True
    assert run.replayed_qualifies is True
    assert run.limitation is None
    assert run.replay_rule_version == REPLAY_RULE_VERSION
    original = session.get(Prediction, generation.prediction_id)
    assert run.replayed_opportunity_score == original.opportunity_score
    assert run.replayed_horizon_days == original.horizon_days


def test_rejected_replay_matches_the_original_decision(session):
    stock, generation = _original_generation(session, StubSignalProvider(predicted_probability=Decimal("0.10")))

    run = replay_generation(
        session, generation, StubSignalProvider(predicted_probability=Decimal("0.10")), replayed_at=REPLAYED_AT
    )

    assert run.matches_original is True
    assert run.replayed_qualifies is False
    assert run.replayed_failed_criteria == ["model_probability"]


def test_future_market_data_never_leaks_into_the_replay(session):
    stock, generation = _original_generation(session, StubSignalProvider())
    control = replay_generation(session, generation, StubSignalProvider(), replayed_at=REPLAYED_AT)

    # price data published well after the original scan date; if it leaked
    # into the point-in-time query, the recomputed features/score would change
    future_timestamp = datetime.combine(SCAN_DATE + timedelta(days=30), time.min, NSE_TIMEZONE)
    session.add(
        MarketPrice(
            stock_id=stock.id,
            timestamp=future_timestamp,
            open=Decimal("500"),
            high=Decimal("600"),
            low=Decimal("400"),
            close=Decimal("550"),
            volume=999_999,
            source="test",
        )
    )
    session.flush()

    leakage_check = replay_generation(session, generation, StubSignalProvider(), replayed_at=REPLAYED_AT)

    assert leakage_check.replayed_opportunity_score == control.replayed_opportunity_score
    assert leakage_check.replayed_horizon_days == control.replayed_horizon_days
    assert leakage_check.replayed_predicted_probability == control.replayed_predicted_probability


def test_no_historical_market_data_produces_an_explicit_limitation(session):
    scan = DailyCandidateScan(scan_date=SCAN_DATE, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = _make_stock(session)
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
    generation = generate_recommendation_for_candidate(
        session,
        candidate,
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )
    # no MarketPrice rows exist for this stock at all

    run = replay_generation(session, generation, StubSignalProvider(), replayed_at=REPLAYED_AT)

    assert run.limitation == LIMITATION_NO_HISTORICAL_DATA
    assert run.replayed_qualifies is None
    assert run.matches_original is None


def test_stale_historical_data_at_replay_time_is_an_explicit_mismatch(session):
    scan = DailyCandidateScan(scan_date=SCAN_DATE, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = _make_stock(session)
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
    generation = generate_recommendation_for_candidate(
        session,
        candidate,
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )
    # market data exists but is stale relative to scan_date (last session well before it)
    stale_last_session = SCAN_DATE - timedelta(days=10)
    _make_rising_price_history(session, stock.id, last_session=stale_last_session)

    run = replay_generation(session, generation, StubSignalProvider(), replayed_at=REPLAYED_AT)

    assert run.limitation == f"{LIMITATION_PREFIX_EXCLUDED_AT_REPLAY}:stale_market_data"
    assert run.matches_original is False  # originally qualified, but replay can't even evaluate it


def test_replay_is_deterministic_across_repeated_runs(session):
    stock, generation = _original_generation(session, StubSignalProvider())

    first = replay_generation(session, generation, StubSignalProvider(), replayed_at=REPLAYED_AT)
    second = replay_generation(session, generation, StubSignalProvider(), replayed_at=REPLAYED_AT)

    assert first.replayed_opportunity_score == second.replayed_opportunity_score
    assert first.replayed_horizon_days == second.replayed_horizon_days
    assert first.replayed_qualifies == second.replayed_qualifies
