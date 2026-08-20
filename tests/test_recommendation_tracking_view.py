from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_snapshot import capture_evidence_snapshot
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.outcome_measurement import measure_outcome
from app.outcomes import evaluate_recommendation
from app.recommendation_tracking import record_daily_observations
from app.recommendation_tracking_view import (
    OUTCOME_STATUS_OPEN,
    build_recommendation_tracking_view,
    get_recommendation_tracking_views,
)
from app.target_stop_loss import publish_recommendation

AS_OF = datetime(2026, 8, 1, tzinfo=timezone.utc)


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


def _make_scan(session, scan_date=date(2026, 8, 1)):
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_prediction(session, scan, symbol, *, as_of=AS_OF, horizon_days_atr=Decimal("0.035")):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector="Energy")
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=horizon_days_atr, data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=as_of)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return session.get(Prediction, generation.prediction_id), stock


def test_active_recommendation_shows_progress_without_an_outcome(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA")
    publish_recommendation(session, prediction, published_at=AS_OF)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("102"), high=Decimal("103"), low=Decimal("101"), close=Decimal("102.5"),
        volume=1000, source="test",
    ))
    session.flush()
    record_daily_observations(session, prediction)

    view = build_recommendation_tracking_view(session, prediction)

    assert view.symbol == "AAA"
    assert view.entry_price == Decimal("100")
    assert view.outcome_status == OUTCOME_STATUS_OPEN
    assert view.outcome is None
    assert view.current_price == Decimal("102.5")
    assert view.current_return == Decimal("0.025")
    assert view.target_progress is not None
    assert view.target_progress > 0
    assert view.publication is not None
    assert view.publication.target_price == Decimal("105.000000")


def test_completed_recommendation_remains_fully_viewable(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA")
    publish_recommendation(session, prediction, published_at=AS_OF)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("106"), high=Decimal("107"), low=Decimal("105"), close=Decimal("106"),
        volume=1000, source="test",
    ))
    session.flush()
    outcome = evaluate_recommendation(session, prediction)
    measure_outcome(session, outcome, measured_at=AS_OF)
    record_daily_observations(session, prediction)

    view = build_recommendation_tracking_view(session, prediction)

    assert view.outcome is not None
    assert view.outcome_status == outcome.outcome
    assert view.outcome_status != OUTCOME_STATUS_OPEN
    assert len(view.observation_history) == 1


def test_missing_market_data_shows_no_current_price_but_original_values_intact(session):
    scan = _make_scan(session)
    prediction, _stock = _make_prediction(session, scan, "AAA")
    publish_recommendation(session, prediction, published_at=AS_OF)
    # deliberately no MarketPrice, no observation recorded at all

    view = build_recommendation_tracking_view(session, prediction)

    assert view.current_price is None
    assert view.current_return is None
    assert view.target_progress is None
    assert view.stop_progress is None
    assert view.entry_price == Decimal("100")
    assert view.horizon_days == 1
    assert view.elapsed_days == 0


def test_evidence_snapshot_is_included_when_captured(session):
    scan = _make_scan(session)
    prediction, _stock = _make_prediction(session, scan, "AAA")
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    view = build_recommendation_tracking_view(session, prediction)

    assert len(view.evidence_snapshot) == 5


def test_original_values_visible_beside_current_state_after_price_moves(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA")
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("120"), high=Decimal("121"), low=Decimal("119"), close=Decimal("120"),
        volume=1000, source="test",
    ))
    session.flush()
    record_daily_observations(session, prediction)

    view = build_recommendation_tracking_view(session, prediction)

    assert view.entry_price == Decimal("100")  # original, unchanged
    assert view.current_price == Decimal("120")  # current, different


def test_no_publication_is_represented_explicitly(session):
    scan = _make_scan(session)
    prediction, _stock = _make_prediction(session, scan, "AAA")
    # deliberately never calling publish_recommendation

    view = build_recommendation_tracking_view(session, prediction)

    assert view.publication is None
    assert view.target_progress is None


def test_views_can_be_filtered_by_symbol_horizon_and_date(session):
    scan = _make_scan(session)
    prediction_a, _ = _make_prediction(session, scan, "AAA", as_of=AS_OF)
    prediction_b, _ = _make_prediction(session, scan, "BBB", as_of=AS_OF + timedelta(days=5))

    by_symbol = get_recommendation_tracking_views(session, symbol="AAA")
    assert [v.prediction_id for v in by_symbol] == [prediction_a.id]

    by_horizon = get_recommendation_tracking_views(session, horizon_days=1)
    assert {v.prediction_id for v in by_horizon} == {prediction_a.id, prediction_b.id}

    by_date = get_recommendation_tracking_views(session, start=AS_OF + timedelta(days=1))
    assert [v.prediction_id for v in by_date] == [prediction_b.id]

    by_prediction_id = get_recommendation_tracking_views(session, prediction_id=prediction_a.id)
    assert [v.prediction_id for v in by_prediction_id] == [prediction_a.id]


def test_tracking_view_never_writes_anything(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA")
    publish_recommendation(session, prediction, published_at=AS_OF)
    before_prediction = (prediction.entry_price, prediction.confidence, prediction.opportunity_score)

    build_recommendation_tracking_view(session, prediction)
    get_recommendation_tracking_views(session)

    after_prediction = (prediction.entry_price, prediction.confidence, prediction.opportunity_score)
    assert before_prediction == after_prediction
