from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DailyCandidateScan, RecommendationGeneration, ScanCandidate, Stock
from app.recommendation_generator import OUTCOME_NOT_QUALIFIED, OUTCOME_QUALIFIED
from app.watchlist_analysis import analyze_watchlist_stock
from app.watchlist_decision_history import (
    DECISION_RULE_VERSION,
    WatchlistDecisionImmutableError,
    WatchlistDecisionSourceMissingError,
    get_watchlist_decision_history,
    record_watchlist_decision,
)
from app.watchlist_intake import add_to_watchlist

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


def _make_scan(session, scan_date=date(2026, 8, 21)):
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
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


def _analyze(session, scan, stock, *, requested_at=AS_OF, as_of_timestamp=AS_OF):
    add_to_watchlist(session, symbol=stock.symbol, requested_at=requested_at)
    return analyze_watchlist_stock(
        session,
        scan_id=scan.id,
        stock_id=stock.id,
        as_of_timestamp=as_of_timestamp,
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )


def test_qualifying_decision_is_recorded_with_full_version_metadata(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock)
    generation = _analyze(session, scan, stock)

    decision = record_watchlist_decision(session, generation)

    assert decision.symbol == stock.symbol
    assert decision.outcome == OUTCOME_QUALIFIED
    assert decision.prediction_id == generation.prediction_id
    assert decision.model_version == "test-model-1"
    assert decision.scoring_contract_version is not None
    assert decision.horizon_selection_version is not None
    assert decision.opportunity_score > 0
    assert decision.decision_rule_version == DECISION_RULE_VERSION


def test_rejected_decision_is_recorded_without_prediction_metadata(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock, predicted_probability=Decimal("0.10"))
    generation = _analyze(session, scan, stock)

    decision = record_watchlist_decision(session, generation)

    assert decision.outcome == OUTCOME_NOT_QUALIFIED
    assert decision.failed_criteria == ["model_probability"]
    assert decision.prediction_id is None
    assert decision.model_version is None
    assert decision.opportunity_score is None


def test_recording_twice_is_idempotent(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock)
    generation = _analyze(session, scan, stock)

    first = record_watchlist_decision(session, generation)
    second = record_watchlist_decision(session, generation)

    assert first.id == second.id
    assert session.query(type(first)).count() == 1


def test_generation_without_watchlist_provenance_raises(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    candidate = _make_eligible_candidate(session, scan, stock)
    from app.recommendation_generator import generate_recommendation_for_candidate

    generation = generate_recommendation_for_candidate(
        session,
        candidate,
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )

    with pytest.raises(WatchlistDecisionSourceMissingError):
        record_watchlist_decision(session, generation)


def test_decision_is_immutable_after_creation(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock)
    generation = _analyze(session, scan, stock)
    decision = record_watchlist_decision(session, generation)

    decision.outcome = OUTCOME_NOT_QUALIFIED
    with pytest.raises(WatchlistDecisionImmutableError, match="outcome"):
        session.flush()
    session.rollback()


def test_history_query_filters_by_symbol_and_time_range_deterministically(session):
    scan1 = _make_scan(session, scan_date=date(2026, 8, 10))
    scan2 = _make_scan(session, scan_date=date(2026, 8, 21))
    stock_a = _make_stock(session, "AAA")
    stock_b = _make_stock(session, "BBB")
    _make_eligible_candidate(session, scan1, stock_a)
    _make_eligible_candidate(session, scan2, stock_b)

    early = datetime(2026, 8, 10, tzinfo=timezone.utc)
    late = datetime(2026, 8, 21, tzinfo=timezone.utc)
    gen_a = _analyze(session, scan1, stock_a, requested_at=early, as_of_timestamp=early)
    gen_b = _analyze(session, scan2, stock_b, requested_at=late, as_of_timestamp=late)
    record_watchlist_decision(session, gen_a)
    record_watchlist_decision(session, gen_b)

    by_symbol = get_watchlist_decision_history(session, symbol="AAA")
    assert [d.symbol for d in by_symbol] == ["AAA"]

    by_range = get_watchlist_decision_history(
        session, start=early, end=early + timedelta(days=1)
    )
    assert [d.symbol for d in by_range] == ["AAA"]

    all_history = get_watchlist_decision_history(session)
    assert [d.symbol for d in all_history] == ["AAA", "BBB"]  # deterministic chronological order
