from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, Prediction, ScanCandidate, Stock
from app.multi_horizon_resolution import (
    CONFLICT_SCORE_MARGIN,
    MULTI_HORIZON_RESOLUTION_VERSION,
    NoOpenRecommendationError,
    get_horizon_views,
    get_resolution_history,
    resolve_multi_horizon_view,
)
from app.user_preferences import HORIZON_BAND_CUSTOM, HORIZON_BAND_MEDIUM, HORIZON_BAND_SHORT, set_user_preference

AS_OF = datetime(2026, 11, 10, tzinfo=timezone.utc)

# Fixed candidate inputs that yield a distinctly different opportunity_score
# per horizon-selecting atr_percent, so a real, non-trivial score spread
# exists between horizons without needing to fabricate scoring logic.
_STRONG = dict(predicted_probability=Decimal("0.95"), confidence=Decimal("0.90"), sma20_distance=Decimal("0.08"), volume_ratio_20d=Decimal("1.80"))
_WEAK = dict(predicted_probability=Decimal("0.61"), confidence=Decimal("0.56"), sma20_distance=Decimal("0.005"), volume_ratio_20d=Decimal("0.80"))


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


_scan_counter = iter(range(100000))


def _make_open_prediction(session, stock, *, atr_percent, inputs, as_of=AS_OF):
    scan_date = AS_OF.date() + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        atr_percent=atr_percent, data_quality_passed=True, model_version="test-model-1", feature_version="FV-001",
        **inputs,
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=as_of)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=as_of, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return session.get(Prediction, generation.prediction_id)


def test_single_open_horizon_has_no_conflict(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    _make_open_prediction(session, stock, atr_percent=Decimal("0.035"), inputs=_STRONG)  # horizon=1

    resolution = resolve_multi_horizon_view(session, user_id="user-1", stock_id=stock.id, resolved_at=AS_OF)

    assert resolution.has_conflict is False
    assert resolution.conflicting_prediction_ids == []
    assert resolution.resolution_rule_version == MULTI_HORIZON_RESOLUTION_VERSION


def test_no_open_recommendation_raises(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()

    with pytest.raises(NoOpenRecommendationError):
        resolve_multi_horizon_view(session, user_id="user-1", stock_id=stock.id, resolved_at=AS_OF)


def test_divergent_scores_across_horizons_are_flagged_as_conflict(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    strong = _make_open_prediction(session, stock, atr_percent=Decimal("0.035"), inputs=_STRONG)  # horizon=1
    weak = _make_open_prediction(session, stock, atr_percent=Decimal("0.001"), inputs=_WEAK)  # horizon=7
    assert abs(strong.opportunity_score - weak.opportunity_score) >= CONFLICT_SCORE_MARGIN

    resolution = resolve_multi_horizon_view(session, user_id="user-1", stock_id=stock.id, resolved_at=AS_OF)

    assert resolution.has_conflict is True
    assert weak.id in resolution.conflicting_prediction_ids
    assert resolution.primary_prediction_id == strong.id  # higher score wins by default


def test_default_preference_prioritizes_short_horizon(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    short_horizon = _make_open_prediction(session, stock, atr_percent=Decimal("0.035"), inputs=_WEAK)  # horizon=1, lower score

    resolution = resolve_multi_horizon_view(session, user_id="user-2", stock_id=stock.id, resolved_at=AS_OF)

    assert resolution.primary_horizon_days == 1
    assert resolution.primary_prediction_id == short_horizon.id


def test_user_preference_influences_which_horizon_is_primary(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    short_strong = _make_open_prediction(session, stock, atr_percent=Decimal("0.035"), inputs=_STRONG)  # horizon=1
    _long_weak = _make_open_prediction(session, stock, atr_percent=Decimal("0.001"), inputs=_WEAK)  # horizon=7

    # user prefers a custom horizon of exactly 7 days -- even though it scores lower
    set_user_preference(session, user_id="user-3", effective_at=AS_OF, horizon_band=HORIZON_BAND_CUSTOM, custom_horizon_days=7)

    resolution = resolve_multi_horizon_view(session, user_id="user-3", stock_id=stock.id, resolved_at=AS_OF)

    assert resolution.primary_horizon_days == 7
    assert resolution.has_conflict is True
    assert short_strong.id in resolution.conflicting_prediction_ids


def test_no_horizon_matches_preference_falls_back_to_best_available(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    only_short = _make_open_prediction(session, stock, atr_percent=Decimal("0.035"), inputs=_STRONG)  # horizon=1

    # user prefers MEDIUM (8-30 days), which nothing currently open satisfies
    set_user_preference(session, user_id="user-4", effective_at=AS_OF, horizon_band=HORIZON_BAND_MEDIUM)

    resolution = resolve_multi_horizon_view(session, user_id="user-4", stock_id=stock.id, resolved_at=AS_OF)

    assert resolution.primary_prediction_id == only_short.id  # never silently empty


def test_horizon_views_preserve_each_prediction_independently(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    _make_open_prediction(session, stock, atr_percent=Decimal("0.035"), inputs=_STRONG)
    _make_open_prediction(session, stock, atr_percent=Decimal("0.001"), inputs=_WEAK)

    views = get_horizon_views(session, stock.id)

    assert len(views) == 2
    assert {v.horizon_days for v in views} == {1, 7}


def test_resolution_history_preserves_every_decision(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    _make_open_prediction(session, stock, atr_percent=Decimal("0.035"), inputs=_STRONG)

    resolve_multi_horizon_view(session, user_id="user-5", stock_id=stock.id, resolved_at=AS_OF)
    resolve_multi_horizon_view(session, user_id="user-5", stock_id=stock.id, resolved_at=AS_OF + timedelta(days=1))

    history = get_resolution_history(session, user_id="user-5", stock_id=stock.id)
    assert len(history) == 2


def test_resolution_never_writes_to_predictions(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    prediction = _make_open_prediction(session, stock, atr_percent=Decimal("0.035"), inputs=_STRONG)
    before = (prediction.opportunity_score, prediction.confidence, prediction.status)

    resolve_multi_horizon_view(session, user_id="user-6", stock_id=stock.id, resolved_at=AS_OF)

    after = (prediction.opportunity_score, prediction.confidence, prediction.status)
    assert before == after
