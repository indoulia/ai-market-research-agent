from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.lifecycle import STATE_EVALUATED, STATE_ISSUED, process_due_lifecycles
from app.models import DailyCandidateScan, MarketPrice, RecommendationLifecycle, ScanCandidate, Stock
from app.watchlist_analysis import analyze_watchlist_stock
from app.watchlist_decision_history import record_watchlist_decision
from app.watchlist_intake import add_to_watchlist
from app.watchlist_outcome_closure import (
    ensure_lifecycle_entries_for_watchlist_decisions,
    ensure_lifecycle_entry_for_watchlist_decision,
)

AS_OF = datetime(2026, 8, 21, tzinfo=timezone.utc)


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
    scan = DailyCandidateScan(scan_date=date(2026, 8, 21), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_stock(session, symbol="RELIANCE"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _make_eligible_candidate(session, scan, stock, **overrides):
    defaults = dict(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
        atr_percent=Decimal("0.035"),  # selects a 1-day horizon (M1.10)
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    defaults.update(overrides)
    candidate = ScanCandidate(**defaults)
    session.add(candidate)
    session.flush()
    return candidate


def _analyze_and_record(session, scan, stock, **overrides):
    add_to_watchlist(session, symbol=stock.symbol, requested_at=AS_OF)
    _make_eligible_candidate(session, scan, stock, **overrides)
    generation = analyze_watchlist_stock(
        session,
        scan_id=scan.id,
        stock_id=stock.id,
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )
    return record_watchlist_decision(session, generation)


def test_qualifying_decision_gets_an_issued_lifecycle_entry(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    decision = _analyze_and_record(session, scan, stock)

    lifecycle = ensure_lifecycle_entry_for_watchlist_decision(session, decision)

    assert lifecycle is not None
    assert lifecycle.state == STATE_ISSUED
    assert lifecycle.recommendation_generation_id == decision.recommendation_generation_id


def test_rejected_decision_gets_no_lifecycle_entry(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    decision = _analyze_and_record(session, scan, stock, predicted_probability=Decimal("0.10"))

    lifecycle = ensure_lifecycle_entry_for_watchlist_decision(session, decision)

    assert lifecycle is None
    assert session.query(RecommendationLifecycle).count() == 0


def test_creating_lifecycle_entry_twice_is_idempotent(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    decision = _analyze_and_record(session, scan, stock)

    first = ensure_lifecycle_entry_for_watchlist_decision(session, decision)
    second = ensure_lifecycle_entry_for_watchlist_decision(session, decision)

    assert first.id == second.id
    assert session.query(RecommendationLifecycle).count() == 1


def test_batch_helper_skips_rejected_decisions(session):
    scan = _make_scan(session)
    qualifying_stock = _make_stock(session, "GOOD")
    rejected_stock = _make_stock(session, "BAD")
    qualifying = _analyze_and_record(session, scan, qualifying_stock)
    rejected = _analyze_and_record(session, scan, rejected_stock, predicted_probability=Decimal("0.10"))

    lifecycles = ensure_lifecycle_entries_for_watchlist_decisions(session, [qualifying, rejected])

    assert len(lifecycles) == 1
    assert lifecycles[0].recommendation_generation_id == qualifying.recommendation_generation_id


def test_watchlist_lifecycle_entry_is_closed_by_the_shared_m1_15_scheduler(session):
    """End-to-end proof that M1.15's process_due_lifecycles (untouched) is the
    real closure mechanism for a watchlist-issued recommendation, exactly as
    it is for an M1.14-selected one."""
    scan = _make_scan(session)
    stock = _make_stock(session)
    decision = _analyze_and_record(session, scan, stock)
    ensure_lifecycle_entry_for_watchlist_decision(session, decision)

    # horizon_days=1 (atr_percent=0.035); one trading session of market data closes it out
    session.add(
        MarketPrice(
            stock_id=stock.id,
            timestamp=AS_OF + timedelta(days=1),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.5"),
            volume=1000,
            source="test",
        )
    )
    session.flush()

    processed = process_due_lifecycles(session)

    assert len(processed) == 1
    assert processed[0].state == STATE_EVALUATED
    assert processed[0].outcome_id is not None
