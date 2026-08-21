from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, ScanCandidate, Stock
from app.portfolio_awareness import (
    ACTION_HELD,
    ACTION_SOLD,
    REASON_ALREADY_ACTIVE_RECOMMENDATION,
    REASON_ALREADY_HELD,
    REASON_SECTOR_CONCENTRATION,
    SECTOR_CONCENTRATION_THRESHOLD,
    InvalidHoldingError,
    UserHoldingImmutableError,
    assess_portfolio_conflict,
    get_current_holdings,
    record_holding,
)
from app.recommendation_selection import select_recommendations_for_scan

AS_OF = datetime(2026, 10, 20, tzinfo=timezone.utc)


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
    scan = DailyCandidateScan(scan_date=date(2026, 10, 20), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_stock(session, symbol, sector="Energy"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector=sector)
    session.add(stock)
    session.flush()
    return stock


def _make_selected_recommendation(session, scan, stock):
    """A high-scoring, system-wide-selected, still-open recommendation."""
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.95"), confidence=Decimal("0.90"), sma20_distance=Decimal("0.08"),
        volume_ratio_20d=Decimal("1.80"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    select_recommendations_for_scan(session, scan.id)


def test_record_holding_validates_action(session):
    stock = _make_stock(session, "AAA")

    with pytest.raises(InvalidHoldingError):
        record_holding(session, user_id="user-1", stock_id=stock.id, action="OWNED", recorded_at=AS_OF)


def test_current_holdings_reflect_the_latest_action(session):
    stock = _make_stock(session, "AAA")
    record_holding(session, user_id="user-1", stock_id=stock.id, action=ACTION_HELD, recorded_at=AS_OF)

    holdings = get_current_holdings(session, "user-1")
    assert [s.symbol for s in holdings] == ["AAA"]

    record_holding(session, user_id="user-1", stock_id=stock.id, action=ACTION_SOLD, recorded_at=AS_OF)
    holdings_after_sale = get_current_holdings(session, "user-1")
    assert holdings_after_sale == ()


def test_no_conflict_for_an_unrelated_stock(session):
    stock = _make_stock(session, "AAA")

    assessment = assess_portfolio_conflict(session, user_id="user-1", candidate_stock_id=stock.id)

    assert assessment.already_held is False
    assert assessment.already_active_recommendation is False
    assert assessment.conflicts == ()


def test_already_held_stock_is_flagged(session):
    stock = _make_stock(session, "AAA")
    record_holding(session, user_id="user-1", stock_id=stock.id, action=ACTION_HELD, recorded_at=AS_OF)

    assessment = assess_portfolio_conflict(session, user_id="user-1", candidate_stock_id=stock.id)

    assert assessment.already_held is True
    assert REASON_ALREADY_HELD in assessment.conflicts


def test_already_active_recommendation_is_flagged(session):
    scan = _make_scan(session)
    stock = _make_stock(session, "AAA")
    _make_selected_recommendation(session, scan, stock)

    assessment = assess_portfolio_conflict(session, user_id="user-1", candidate_stock_id=stock.id)

    assert assessment.already_active_recommendation is True
    assert REASON_ALREADY_ACTIVE_RECOMMENDATION in assessment.conflicts


def test_sector_concentration_is_detected(session):
    scan = _make_scan(session)
    held_stocks = []
    for i in range(SECTOR_CONCENTRATION_THRESHOLD - 1):
        stock = _make_stock(session, f"H{i}", sector="Energy")
        record_holding(session, user_id="user-1", stock_id=stock.id, action=ACTION_HELD, recorded_at=AS_OF)
        held_stocks.append(stock)
    candidate = _make_stock(session, "CANDIDATE", sector="Energy")

    assessment = assess_portfolio_conflict(session, user_id="user-1", candidate_stock_id=candidate.id)

    assert assessment.sector_exposure_count == SECTOR_CONCENTRATION_THRESHOLD - 1
    assert assessment.sector_concentration_warning is True
    assert any(c.startswith(REASON_SECTOR_CONCENTRATION) for c in assessment.conflicts)


def test_different_sector_holdings_do_not_trigger_concentration(session):
    for i in range(SECTOR_CONCENTRATION_THRESHOLD):
        stock = _make_stock(session, f"H{i}", sector="Technology")
        record_holding(session, user_id="user-1", stock_id=stock.id, action=ACTION_HELD, recorded_at=AS_OF)
    candidate = _make_stock(session, "CANDIDATE", sector="Energy")

    assessment = assess_portfolio_conflict(session, user_id="user-1", candidate_stock_id=candidate.id)

    assert assessment.sector_concentration_warning is False
    assert assessment.conflicts == ()


def test_assessment_never_writes_anything(session):
    stock = _make_stock(session, "AAA")
    record_holding(session, user_id="user-1", stock_id=stock.id, action=ACTION_HELD, recorded_at=AS_OF)
    before = session.query(Stock).count()

    assess_portfolio_conflict(session, user_id="user-1", candidate_stock_id=stock.id)

    after = session.query(Stock).count()
    assert before == after


def test_holding_event_is_immutable_after_creation(session):
    stock = _make_stock(session, "AAA")
    holding = record_holding(session, user_id="user-1", stock_id=stock.id, action=ACTION_HELD, recorded_at=AS_OF)

    holding.action = ACTION_SOLD
    with pytest.raises(UserHoldingImmutableError, match="action"):
        session.flush()
    session.rollback()


def test_conflict_assessment_is_reproducible(session):
    stock = _make_stock(session, "AAA")
    record_holding(session, user_id="user-1", stock_id=stock.id, action=ACTION_HELD, recorded_at=AS_OF)

    first = assess_portfolio_conflict(session, user_id="user-1", candidate_stock_id=stock.id)
    second = assess_portfolio_conflict(session, user_id="user-1", candidate_stock_id=stock.id)

    assert first == second
