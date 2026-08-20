from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.recommendation_generator import generate_recommendation_for_candidate
from app.recommendation_selection import select_recommendations_for_scan
from app.lifecycle import (
    LIFECYCLE_VERSION,
    STATE_AWAITING_HORIZON,
    STATE_EVALUATED,
    STATE_ISSUED,
    STATE_UNEVALUABLE,
    advance_lifecycle,
    ensure_lifecycle_entries_for_scan,
    process_due_lifecycles,
)

AS_OF = datetime(2026, 8, 20, tzinfo=timezone.utc)


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


def _make_scan(session, scan_date=date(2026, 8, 20)):
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=0, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_qualified(session, scan, symbol, *, atr_percent=Decimal("0.035"), entry_price=Decimal("100")):
    """Runs a candidate through the real M1.13 generator so its horizon comes from
    M1.10's real selection rule (atr_percent controls which of 1/3/5/7 is chosen)."""
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=Decimal("0.75"),
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
        atr_percent=atr_percent,
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
        entry_price=entry_price,
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )
    return stock, generation


def _make_prices(session, stock_id, closes, *, start=AS_OF, valid=True):
    for offset, close in enumerate(closes, start=1):
        close = Decimal(str(close))
        session.add(
            MarketPrice(
                stock_id=stock_id,
                timestamp=start + timedelta(days=offset),
                open=close if valid else Decimal("0"),
                high=close + Decimal("1") if valid else Decimal("-5"),
                low=close - Decimal("1") if valid else Decimal("999"),
                close=close,
                volume=1000 if valid else 0,
                source="test",
            )
        )
    session.flush()


def test_ensure_lifecycle_entries_creates_issued_rows_only_for_selected(session):
    scan = _make_scan(session)
    _make_qualified(session, scan, "TOP", atr_percent=Decimal("0.035"))
    _make_qualified(session, scan, "BOTTOM", atr_percent=Decimal("0.035"))
    select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"), daily_limit=1)

    lifecycles = ensure_lifecycle_entries_for_scan(session, scan.id)

    assert len(lifecycles) == 1
    assert lifecycles[0].state == STATE_ISSUED
    assert lifecycles[0].lifecycle_rule_version == LIFECYCLE_VERSION
    assert lifecycles[0].check_count == 0


def test_ensure_lifecycle_entries_is_idempotent(session):
    scan = _make_scan(session)
    _make_qualified(session, scan, "RELIANCE")
    select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"), daily_limit=5)

    first = ensure_lifecycle_entries_for_scan(session, scan.id)
    second = ensure_lifecycle_entries_for_scan(session, scan.id)

    assert [row.id for row in first] == [row.id for row in second]
    assert session.query(Prediction).count() == 1


def test_ensure_lifecycle_entries_with_no_selections_is_empty(session):
    scan = _make_scan(session)

    assert ensure_lifecycle_entries_for_scan(session, scan.id) == ()


@pytest.mark.parametrize(
    "atr_percent,horizon_days",
    [
        (Decimal("0.035"), 1),
        (Decimal("0.020"), 3),
        (Decimal("0.010"), 5),
        (Decimal("0.001"), 7),
    ],
)
def test_process_due_lifecycles_evaluates_at_selected_horizon(session, atr_percent, horizon_days):
    scan = _make_scan(session)
    stock, generation = _make_qualified(session, scan, "HORZ", atr_percent=atr_percent)
    prediction = session.get(Prediction, generation.prediction_id)
    assert prediction.horizon_days == horizon_days
    select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"), daily_limit=5)
    ensure_lifecycle_entries_for_scan(session, scan.id)
    _make_prices(session, stock.id, [100] * (horizon_days + 2))

    processed = process_due_lifecycles(session)

    assert len(processed) == 1
    assert processed[0].state == STATE_EVALUATED
    assert processed[0].outcome_id is not None
    assert processed[0].check_count == 1


def test_process_due_lifecycles_awaits_horizon_when_data_insufficient(session):
    scan = _make_scan(session)
    stock, generation = _make_qualified(session, scan, "SLOW", atr_percent=Decimal("0.010"))  # horizon=5
    select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"), daily_limit=5)
    ensure_lifecycle_entries_for_scan(session, scan.id)
    _make_prices(session, stock.id, [100, 100, 100])  # only 3 of 5 sessions

    processed = process_due_lifecycles(session)

    assert processed[0].state == STATE_AWAITING_HORIZON
    assert processed[0].outcome_id is None
    assert processed[0].check_count == 1


def test_process_due_lifecycles_marks_unevaluable_for_invalid_price_data(session):
    scan = _make_scan(session)
    stock, generation = _make_qualified(session, scan, "BADDATA", atr_percent=Decimal("0.035"))  # horizon=1
    select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"), daily_limit=5)
    ensure_lifecycle_entries_for_scan(session, scan.id)
    _make_prices(session, stock.id, [100], valid=False)

    processed = process_due_lifecycles(session)

    assert processed[0].state == STATE_UNEVALUABLE
    assert processed[0].outcome_id is not None


def test_process_due_lifecycles_recovers_after_interruption(session):
    scan = _make_scan(session)
    stock, generation = _make_qualified(session, scan, "RESUME", atr_percent=Decimal("0.010"))  # horizon=5
    select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"), daily_limit=5)
    ensure_lifecycle_entries_for_scan(session, scan.id)
    _make_prices(session, stock.id, [100, 100, 100])  # interrupted: only 3 of 5 sessions so far

    first_pass = process_due_lifecycles(session)
    assert first_pass[0].state == STATE_AWAITING_HORIZON
    assert first_pass[0].check_count == 1

    # More trading days arrive after the "interruption"; the scheduler resumes on the
    # same lifecycle row rather than creating a new one.
    _make_prices(session, stock.id, [101, 102], start=AS_OF + timedelta(days=3))

    second_pass = process_due_lifecycles(session)
    assert second_pass[0].id == first_pass[0].id
    assert second_pass[0].state == STATE_EVALUATED
    assert second_pass[0].check_count == 2


def test_process_due_lifecycles_is_idempotent_once_terminal(session):
    scan = _make_scan(session)
    stock, generation = _make_qualified(session, scan, "DONE", atr_percent=Decimal("0.035"))  # horizon=1
    select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"), daily_limit=5)
    ensure_lifecycle_entries_for_scan(session, scan.id)
    _make_prices(session, stock.id, [101])

    first_pass = process_due_lifecycles(session)
    second_pass = process_due_lifecycles(session)

    assert first_pass[0].state == STATE_EVALUATED
    assert second_pass == ()  # terminal rows aren't even selected for re-processing
    assert first_pass[0].check_count == 1


def test_advance_lifecycle_is_a_noop_for_a_terminal_row(session):
    scan = _make_scan(session)
    stock, generation = _make_qualified(session, scan, "NOOP", atr_percent=Decimal("0.035"))  # horizon=1
    select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"), daily_limit=5)
    (lifecycle,) = ensure_lifecycle_entries_for_scan(session, scan.id)
    _make_prices(session, stock.id, [101])

    evaluated = advance_lifecycle(session, lifecycle)
    assert evaluated.state == STATE_EVALUATED

    repeated = advance_lifecycle(session, evaluated)
    assert repeated.check_count == evaluated.check_count
    assert repeated.state == STATE_EVALUATED


def test_process_due_lifecycles_scoped_to_one_scan(session):
    scan_a = _make_scan(session, scan_date=date(2026, 8, 20))
    scan_b = _make_scan(session, scan_date=date(2026, 8, 21))
    stock_a, gen_a = _make_qualified(session, scan_a, "SCANA", atr_percent=Decimal("0.035"))
    stock_b, gen_b = _make_qualified(session, scan_b, "SCANB", atr_percent=Decimal("0.035"))
    select_recommendations_for_scan(session, scan_a.id, min_score=Decimal("0"), daily_limit=5)
    select_recommendations_for_scan(session, scan_b.id, min_score=Decimal("0"), daily_limit=5)
    ensure_lifecycle_entries_for_scan(session, scan_a.id)
    ensure_lifecycle_entries_for_scan(session, scan_b.id)
    _make_prices(session, stock_a.id, [101])
    _make_prices(session, stock_b.id, [101])

    processed = process_due_lifecycles(session, scan_id=scan_a.id)

    assert len(processed) == 1
    assert processed[0].recommendation_generation_id == gen_a.id
    remaining_open = process_due_lifecycles(session)
    assert len(remaining_open) == 1
    assert remaining_open[0].recommendation_generation_id == gen_b.id
