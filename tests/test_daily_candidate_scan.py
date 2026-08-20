from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.market_data.quality import NSE_TIMEZONE
from app.models import MarketPrice, ScanCandidate, Stock
from app.scan import (
    UNIVERSE_VERSION,
    CandidateSignals,
    run_daily_candidate_scan,
)


class StubSignalProvider:
    model_version = "test-model-1"

    def predict(self, stock_id, features):
        return CandidateSignals(predicted_probability=Decimal("0.65"), confidence=Decimal("0.70"))


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


def _make_stock(session, symbol="RELIANCE", is_active=True):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=is_active)
    session.add(stock)
    session.flush()
    return stock


def _make_price_rows(session, stock_id, last_session: date, count: int, base_price=Decimal("100")):
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


def test_eligible_stock_with_sufficient_history_is_marked_eligible_with_signals(session):
    stock = _make_stock(session)
    scan_date = date(2026, 8, 20)
    _make_price_rows(session, stock.id, scan_date, count=25)

    summary = run_daily_candidate_scan(session, scan_date, StubSignalProvider())

    assert summary.scan.eligible_count == 1
    assert summary.scan.excluded_count == 0
    assert len(summary.candidates) == 1
    candidate = summary.candidates[0]
    assert candidate.eligible is True
    assert candidate.exclusion_reason is None
    assert candidate.predicted_probability == Decimal("0.65")
    assert candidate.confidence == Decimal("0.70")
    assert candidate.data_quality_passed is True
    assert candidate.model_version == "test-model-1"


def test_missing_market_data_is_excluded_explicitly(session):
    _make_stock(session)
    scan_date = date(2026, 8, 20)

    summary = run_daily_candidate_scan(session, scan_date, StubSignalProvider())

    assert summary.scan.eligible_count == 0
    assert summary.scan.excluded_count == 1
    candidate = summary.candidates[0]
    assert candidate.eligible is False
    assert candidate.exclusion_reason == "missing_market_data"
    assert candidate.predicted_probability is None


def test_stale_market_data_is_excluded_explicitly(session):
    stock = _make_stock(session)
    latest_available_session = date(2026, 8, 18)
    scan_date = date(2026, 8, 20)
    _make_price_rows(session, stock.id, latest_available_session, count=25)

    summary = run_daily_candidate_scan(session, scan_date, StubSignalProvider())

    candidate = summary.candidates[0]
    assert candidate.eligible is False
    assert candidate.exclusion_reason == "stale_market_data"
    assert candidate.data_quality_passed is False


def test_insufficient_history_is_excluded_as_invalid_market_data(session):
    stock = _make_stock(session)
    scan_date = date(2026, 8, 20)
    _make_price_rows(session, stock.id, scan_date, count=5)

    summary = run_daily_candidate_scan(session, scan_date, StubSignalProvider())

    candidate = summary.candidates[0]
    assert candidate.eligible is False
    assert candidate.exclusion_reason == "invalid_market_data"
    assert candidate.data_quality_passed is False


def test_inactive_stock_is_not_included_in_universe(session):
    stock = _make_stock(session, is_active=False)
    scan_date = date(2026, 8, 20)
    _make_price_rows(session, stock.id, scan_date, count=25)

    summary = run_daily_candidate_scan(session, scan_date, StubSignalProvider())

    assert summary.candidates == ()
    assert summary.scan.eligible_count == 0
    assert summary.scan.excluded_count == 0


def test_empty_universe_produces_scan_with_no_candidates(session):
    scan_date = date(2026, 8, 20)

    summary = run_daily_candidate_scan(session, scan_date, StubSignalProvider())

    assert summary.candidates == ()
    assert summary.scan.eligible_count == 0
    assert summary.scan.excluded_count == 0


def test_rerunning_same_scan_date_and_universe_version_does_not_duplicate(session):
    stock = _make_stock(session)
    scan_date = date(2026, 8, 20)
    _make_price_rows(session, stock.id, scan_date, count=25)

    first = run_daily_candidate_scan(session, scan_date, StubSignalProvider())
    second = run_daily_candidate_scan(session, scan_date, StubSignalProvider())

    assert first.scan.id == second.scan.id
    assert session.query(ScanCandidate).count() == 1
    from app.models import DailyCandidateScan

    assert session.query(DailyCandidateScan).count() == 1


def test_different_universe_version_creates_a_separate_scan(session):
    stock = _make_stock(session)
    scan_date = date(2026, 8, 20)
    _make_price_rows(session, stock.id, scan_date, count=25)

    first = run_daily_candidate_scan(session, scan_date, StubSignalProvider(), universe_version=UNIVERSE_VERSION)
    second = run_daily_candidate_scan(session, scan_date, StubSignalProvider(), universe_version="DCS-002")

    assert first.scan.id != second.scan.id
    assert session.query(ScanCandidate).count() == 2
