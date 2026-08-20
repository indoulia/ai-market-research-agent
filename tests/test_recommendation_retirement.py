from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.lifecycle import LIFECYCLE_VERSION, STATE_ISSUED, advance_lifecycle
from app.models import DailyCandidateScan, MarketPrice, RecommendationLifecycle, ScanCandidate, Stock
from app.recommendation_generator import generate_recommendation_for_candidate
from app.recommendation_retirement import (
    DEFAULT_ARCHIVE_RETENTION,
    REASON_HORIZON_COMPLETED,
    RETIREMENT_RULE_VERSION,
    RecommendationNotCompletedError,
    RecommendationRetirementImmutableError,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_COMPLETED,
    STATUS_RETIRED,
    get_active_prediction_ids,
    get_archived_retirements,
    get_recommendation_status,
    retire_recommendation,
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


def _make_generation(session, scan, symbol):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
        atr_percent=Decimal("0.035"),  # horizon=1
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    generation = generate_recommendation_for_candidate(
        session, candidate, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return stock, generation


def _make_lifecycle(session, generation):
    lifecycle = RecommendationLifecycle(
        recommendation_generation_id=generation.id, state=STATE_ISSUED, lifecycle_rule_version=LIFECYCLE_VERSION,
    )
    session.add(lifecycle)
    session.commit()
    session.refresh(lifecycle)
    return lifecycle


def test_cannot_retire_an_active_recommendation(session):
    scan = _make_scan(session)
    stock, generation = _make_generation(session, scan, "RELIANCE")
    lifecycle = _make_lifecycle(session, generation)
    # no market data yet -> still AWAITING_HORIZON / ISSUED

    with pytest.raises(RecommendationNotCompletedError):
        retire_recommendation(session, lifecycle, retired_at=AS_OF)


def test_retiring_a_completed_recommendation_succeeds(session):
    scan = _make_scan(session)
    stock, generation = _make_generation(session, scan, "RELIANCE")
    lifecycle = _make_lifecycle(session, generation)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100.5"),
        volume=1000, source="test",
    ))
    session.flush()
    lifecycle = advance_lifecycle(session, lifecycle)
    assert lifecycle.state == "EVALUATED"

    retirement = retire_recommendation(session, lifecycle, retired_at=AS_OF)

    assert retirement.retirement_reason == REASON_HORIZON_COMPLETED
    assert retirement.lifecycle_state_at_retirement == "EVALUATED"
    assert retirement.retirement_rule_version == RETIREMENT_RULE_VERSION


def test_retiring_twice_is_idempotent(session):
    scan = _make_scan(session)
    stock, generation = _make_generation(session, scan, "RELIANCE")
    lifecycle = _make_lifecycle(session, generation)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100.5"),
        volume=1000, source="test",
    ))
    session.flush()
    lifecycle = advance_lifecycle(session, lifecycle)

    first = retire_recommendation(session, lifecycle, retired_at=AS_OF)
    second = retire_recommendation(session, lifecycle, retired_at=AS_OF + timedelta(days=1))

    assert first.id == second.id
    assert first.retired_at == second.retired_at


def test_status_transitions_through_the_full_lifecycle(session):
    scan = _make_scan(session)
    stock, generation = _make_generation(session, scan, "RELIANCE")
    lifecycle = _make_lifecycle(session, generation)
    prediction_id = generation.prediction_id

    assert get_recommendation_status(session, prediction_id, now=AS_OF) == STATUS_ACTIVE

    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100.5"),
        volume=1000, source="test",
    ))
    session.flush()
    lifecycle = advance_lifecycle(session, lifecycle)
    assert get_recommendation_status(session, prediction_id, now=AS_OF) == STATUS_COMPLETED

    retire_recommendation(session, lifecycle, retired_at=AS_OF)
    assert get_recommendation_status(session, prediction_id, now=AS_OF + timedelta(days=1)) == STATUS_RETIRED

    far_future = AS_OF + DEFAULT_ARCHIVE_RETENTION + timedelta(days=1)
    assert get_recommendation_status(session, prediction_id, now=far_future) == STATUS_ARCHIVED


def test_prediction_with_no_lifecycle_row_is_active(session):
    assert get_recommendation_status(session, 999999, now=AS_OF) == STATUS_ACTIVE


def test_active_prediction_ids_excludes_completed_recommendations(session):
    scan = _make_scan(session)
    active_stock, active_generation = _make_generation(session, scan, "ACTIVE1")
    _make_lifecycle(session, active_generation)

    completed_stock, completed_generation = _make_generation(session, scan, "COMPLETED1")
    completed_lifecycle = _make_lifecycle(session, completed_generation)
    session.add(MarketPrice(
        stock_id=completed_stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100.5"),
        volume=1000, source="test",
    ))
    session.flush()
    advance_lifecycle(session, completed_lifecycle)

    active_ids = get_active_prediction_ids(session)

    assert active_generation.prediction_id in active_ids
    assert completed_generation.prediction_id not in active_ids


def test_get_archived_retirements_only_returns_those_past_retention(session):
    scan = _make_scan(session)
    stock, generation = _make_generation(session, scan, "RELIANCE")
    lifecycle = _make_lifecycle(session, generation)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100.5"),
        volume=1000, source="test",
    ))
    session.flush()
    lifecycle = advance_lifecycle(session, lifecycle)
    retire_recommendation(session, lifecycle, retired_at=AS_OF)

    not_yet = get_archived_retirements(session, now=AS_OF + timedelta(days=1))
    assert not_yet == ()

    far_future = AS_OF + DEFAULT_ARCHIVE_RETENTION + timedelta(days=1)
    archived = get_archived_retirements(session, now=far_future)
    assert len(archived) == 1


def test_retirement_is_immutable_after_creation(session):
    scan = _make_scan(session)
    stock, generation = _make_generation(session, scan, "RELIANCE")
    lifecycle = _make_lifecycle(session, generation)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100.5"),
        volume=1000, source="test",
    ))
    session.flush()
    lifecycle = advance_lifecycle(session, lifecycle)
    retirement = retire_recommendation(session, lifecycle, retired_at=AS_OF)

    retirement.retirement_reason = "SOMETHING_ELSE"
    with pytest.raises(RecommendationRetirementImmutableError, match="retirement_reason"):
        session.flush()
    session.rollback()
