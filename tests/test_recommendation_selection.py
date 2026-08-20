from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DailyCandidateScan, RecommendationSelection, ScanCandidate, Stock
from app.recommendation_generator import generate_recommendation_for_candidate
from app.recommendation_selection import (
    DEFAULT_DAILY_LIMIT,
    MIN_SCORE_FOR_SELECTION,
    REASON_BELOW_MIN_SCORE,
    REASON_DAILY_LIMIT_EXCEEDED,
    REASON_SELECTED,
    SELECTION_VERSION,
    select_recommendations_for_scan,
)


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
    scan = DailyCandidateScan(scan_date=date(2026, 8, 20), universe_version="DCS-001", eligible_count=0, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_qualified(session, scan, symbol, *, predicted_probability=Decimal("0.72"), confidence=Decimal("0.80")):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=predicted_probability,
        confidence=confidence,
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
        as_of_timestamp=datetime(2026, 8, 20, tzinfo=timezone.utc),
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )
    return generation


def test_ranks_qualifying_candidates_by_score_descending(session):
    scan = _make_scan(session)
    low = _make_qualified(session, scan, "LOW", predicted_probability=Decimal("0.61"))
    high = _make_qualified(session, scan, "HIGH", predicted_probability=Decimal("0.99"))
    mid = _make_qualified(session, scan, "MID", predicted_probability=Decimal("0.80"))

    selections = select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"), daily_limit=10)

    by_generation = {s.recommendation_generation_id: s for s in selections}
    assert by_generation[high.id].rank == 1
    assert by_generation[mid.id].rank == 2
    assert by_generation[low.id].rank == 3
    assert all(s.selected for s in selections)
    assert all(s.selection_rule_version == SELECTION_VERSION for s in selections)


def test_enforces_daily_limit(session):
    scan = _make_scan(session)
    generations = [
        _make_qualified(session, scan, f"S{i:02d}", predicted_probability=Decimal("0.60") + Decimal(i) / 100)
        for i in range(7)
    ]

    selections = select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"), daily_limit=3)

    selected = [s for s in selections if s.selected]
    exceeded = [s for s in selections if s.selection_reason == REASON_DAILY_LIMIT_EXCEEDED]
    assert len(selected) == 3
    assert len(exceeded) == 4
    assert {s.rank for s in selected} == {1, 2, 3}
    assert {s.rank for s in exceeded} == {4, 5, 6, 7}
    assert len(generations) == 7


def test_excludes_below_min_score(session):
    scan = _make_scan(session)
    generation = _make_qualified(session, scan, "WEAK", predicted_probability=Decimal("0.61"))

    selections = select_recommendations_for_scan(session, scan.id, min_score=Decimal("99.99"), daily_limit=DEFAULT_DAILY_LIMIT)

    assert len(selections) == 1
    assert selections[0].recommendation_generation_id == generation.id
    assert selections[0].selected is False
    assert selections[0].selection_reason == REASON_BELOW_MIN_SCORE
    assert selections[0].rank is None


def test_boundary_score_exactly_at_min_is_selected(session):
    scan = _make_scan(session)
    generation = _make_qualified(session, scan, "EDGE")
    from app.models import Prediction

    exact_score = session.get(Prediction, generation.prediction_id).opportunity_score

    selections = select_recommendations_for_scan(session, scan.id, min_score=exact_score, daily_limit=DEFAULT_DAILY_LIMIT)

    assert selections[0].selection_reason == REASON_SELECTED
    assert selections[0].selected is True
    assert selections[0].rank == 1


def test_ties_are_broken_deterministically_by_symbol(session):
    scan = _make_scan(session)
    zebra = _make_qualified(session, scan, "ZEBRA")
    alpha = _make_qualified(session, scan, "ALPHA")

    selections = select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"), daily_limit=10)

    by_generation = {s.recommendation_generation_id: s for s in selections}
    assert by_generation[alpha.id].rank == 1
    assert by_generation[zebra.id].rank == 2


def test_empty_input_produces_no_selections(session):
    scan = _make_scan(session)

    selections = select_recommendations_for_scan(session, scan.id)

    assert selections == ()
    assert session.query(RecommendationSelection).count() == 0


def test_reselecting_same_scan_is_idempotent(session):
    scan = _make_scan(session)
    _make_qualified(session, scan, "RELIANCE")

    first = select_recommendations_for_scan(session, scan.id, min_score=Decimal("0"))
    second = select_recommendations_for_scan(session, scan.id, min_score=Decimal("99.99"))

    assert [s.id for s in first] == [s.id for s in second]
    assert session.query(RecommendationSelection).count() == 1
