from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.recommendation_revalidation import (
    OUTCOME_EXPIRED,
    OUTCOME_UNCHANGED,
    OUTCOME_UPDATED,
    OUTCOME_WITHDRAWN,
    REVALIDATION_ENGINE_VERSION,
    get_revalidation_history,
    revalidate_recommendation,
)
from app.recommendation_tracking import record_daily_observations
from app.target_stop_loss import publish_recommendation

AS_OF = datetime(2026, 11, 20, tzinfo=timezone.utc)

_scan_counter = iter(range(100000))


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


def _make_prediction(session, symbol="AAA", *, model_version="test-model-1", atr_percent=Decimal("0.035")):
    scan_date = AS_OF.date() + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=atr_percent, data_quality_passed=True,
        model_version=model_version, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    publish_recommendation(session, prediction, published_at=AS_OF)
    return prediction, stock


def _add_price_and_track(session, prediction, stock, *, close, at):
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=at,
        open=close, high=close + Decimal("1"), low=close - Decimal("1"), close=close,
        volume=1000, source="test",
    ))
    session.flush()
    record_daily_observations(session, prediction)


def test_normal_case_is_unchanged(session):
    prediction, stock = _make_prediction(session, atr_percent=Decimal("0.001"))  # horizon=7
    _add_price_and_track(session, prediction, stock, close=Decimal("101"), at=AS_OF + timedelta(days=1))

    outcome = revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))

    assert outcome.outcome == OUTCOME_UNCHANGED
    assert outcome.revalidation_engine_version == REVALIDATION_ENGINE_VERSION


def test_horizon_expiry_is_detected(session):
    prediction, stock = _make_prediction(session)  # horizon=1
    _add_price_and_track(session, prediction, stock, close=Decimal("101"), at=AS_OF + timedelta(days=1))

    outcome = revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))

    assert outcome.outcome == OUTCOME_EXPIRED
    assert "horizon" in outcome.reason


def test_stop_loss_proximity_triggers_withdrawn(session):
    prediction, stock = _make_prediction(session, atr_percent=Decimal("0.001"))  # horizon=7
    # downside is 3%; a return of -2.8% is within 90% of the stop (>= 2.7%)
    _add_price_and_track(session, prediction, stock, close=Decimal("97.2"), at=AS_OF + timedelta(days=1))

    outcome = revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))

    assert outcome.outcome == OUTCOME_WITHDRAWN
    assert "stop-loss" in outcome.reason


def test_stale_market_data_triggers_withdrawn(session):
    prediction, stock = _make_prediction(session, atr_percent=Decimal("0.001"))  # horizon=7
    _add_price_and_track(session, prediction, stock, close=Decimal("101"), at=AS_OF + timedelta(days=1))

    much_later = AS_OF + timedelta(days=5)
    outcome = revalidate_recommendation(session, prediction, checked_at=much_later)

    assert outcome.outcome == OUTCOME_WITHDRAWN
    assert "market data" in outcome.reason


def test_model_version_change_triggers_updated(session):
    prediction, stock = _make_prediction(session, model_version="test-model-1", atr_percent=Decimal("0.001"))  # horizon=7
    _add_price_and_track(session, prediction, stock, close=Decimal("101"), at=AS_OF + timedelta(days=1))
    # a newer prediction (different stock) using a newer model version
    _make_prediction(session, symbol="BBB", model_version="test-model-2", atr_percent=Decimal("0.001"))

    outcome = revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))

    assert outcome.outcome == OUTCOME_UPDATED
    assert "model version" in outcome.reason


def test_target_proximity_triggers_updated(session):
    prediction, stock = _make_prediction(session, atr_percent=Decimal("0.001"))  # horizon=7
    # upside is 5%; a return of 4.6% is within 90% of the target (>= 4.5%)
    _add_price_and_track(session, prediction, stock, close=Decimal("104.6"), at=AS_OF + timedelta(days=1))

    outcome = revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))

    assert outcome.outcome == OUTCOME_UPDATED
    assert "target" in outcome.reason


def test_revalidation_is_idempotent_for_the_same_checked_at(session):
    prediction, stock = _make_prediction(session)
    _add_price_and_track(session, prediction, stock, close=Decimal("101"), at=AS_OF + timedelta(days=1))
    checked_at = AS_OF + timedelta(days=1)

    first = revalidate_recommendation(session, prediction, checked_at=checked_at)
    second = revalidate_recommendation(session, prediction, checked_at=checked_at)

    assert first.id == second.id
    assert len(get_revalidation_history(session, prediction.id)) == 1


def test_revalidation_never_writes_to_prediction(session):
    prediction, stock = _make_prediction(session)
    _add_price_and_track(session, prediction, stock, close=Decimal("101"), at=AS_OF + timedelta(days=1))
    before = (prediction.status, prediction.opportunity_score, prediction.model_version)

    revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))

    after = (prediction.status, prediction.opportunity_score, prediction.model_version)
    assert before == after


def test_history_retains_multiple_checks_over_time(session):
    prediction, stock = _make_prediction(session, atr_percent=Decimal("0.001"))  # horizon=7
    _add_price_and_track(session, prediction, stock, close=Decimal("101"), at=AS_OF + timedelta(days=1))

    revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))
    revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=2))

    history = get_revalidation_history(session, prediction.id)
    assert len(history) == 2
