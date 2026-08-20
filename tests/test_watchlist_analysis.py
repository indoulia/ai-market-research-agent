from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_WATCHLIST
from app.models import DailyCandidateScan, Prediction, ScanCandidate, Stock
from app.recommendation_generator import OUTCOME_NOT_QUALIFIED, OUTCOME_QUALIFIED, CandidateNotEligibleError
from app.watchlist_analysis import StockNotOnWatchlistError, analyze_watchlist_stock
from app.watchlist_intake import add_to_watchlist, remove_from_watchlist

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
        atr_percent=Decimal("0.035"),
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    defaults.update(overrides)
    candidate = ScanCandidate(**defaults)
    session.add(candidate)
    session.flush()
    return candidate


def _generation_kwargs():
    return dict(
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )


def test_active_watchlist_stock_that_qualifies_is_analyzed_and_selected(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock)
    add_to_watchlist(session, symbol=stock.symbol, requested_at=AS_OF)

    generation = analyze_watchlist_stock(session, scan_id=scan.id, stock_id=stock.id, **_generation_kwargs())

    assert generation.outcome == OUTCOME_QUALIFIED
    assert generation.prediction_id is not None
    recommendation = session.get(Prediction, generation.prediction_id)
    assert recommendation.opportunity_score > 0


def test_watchlist_membership_cannot_bypass_positive_consensus(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock, predicted_probability=Decimal("0.10"))
    add_to_watchlist(session, symbol=stock.symbol, requested_at=AS_OF)

    generation = analyze_watchlist_stock(session, scan_id=scan.id, stock_id=stock.id, **_generation_kwargs())

    assert generation.outcome == OUTCOME_NOT_QUALIFIED
    assert generation.failed_criteria == ["model_probability"]
    assert generation.prediction_id is None
    assert session.query(Prediction).count() == 0


def test_stale_or_excluded_scan_data_raises_instead_of_analyzing(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=False, exclusion_reason="stale_market_data", data_quality_passed=False
    )
    session.add(candidate)
    session.flush()
    add_to_watchlist(session, symbol=stock.symbol, requested_at=AS_OF)

    with pytest.raises(CandidateNotEligibleError, match="stale_market_data"):
        analyze_watchlist_stock(session, scan_id=scan.id, stock_id=stock.id, **_generation_kwargs())


def test_inactive_watchlist_stock_is_rejected_before_any_analysis(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock)
    add_to_watchlist(session, symbol=stock.symbol, requested_at=AS_OF)
    remove_from_watchlist(session, symbol=stock.symbol, requested_at=AS_OF)

    with pytest.raises(StockNotOnWatchlistError):
        analyze_watchlist_stock(session, scan_id=scan.id, stock_id=stock.id, **_generation_kwargs())
    assert session.query(Prediction).count() == 0


def test_never_watchlisted_stock_is_rejected(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock)

    with pytest.raises(StockNotOnWatchlistError):
        analyze_watchlist_stock(session, scan_id=scan.id, stock_id=stock.id, **_generation_kwargs())


def test_repeated_analysis_is_idempotent(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock)
    add_to_watchlist(session, symbol=stock.symbol, requested_at=AS_OF)

    first = analyze_watchlist_stock(session, scan_id=scan.id, stock_id=stock.id, **_generation_kwargs())
    second = analyze_watchlist_stock(session, scan_id=scan.id, stock_id=stock.id, **_generation_kwargs())

    assert first.id == second.id
    assert session.query(Prediction).count() == 1


def test_analysis_is_recorded_with_watchlist_provenance(session):
    from app.models import DiscoveryRecord

    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock)
    add_to_watchlist(session, symbol=stock.symbol, requested_at=AS_OF)

    analyze_watchlist_stock(session, scan_id=scan.id, stock_id=stock.id, **_generation_kwargs())

    record = session.query(DiscoveryRecord).filter_by(scan_id=scan.id, stock_id=stock.id).one()
    assert record.source == SOURCE_WATCHLIST
    assert record.recommendation_generation_id is not None
