from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.market_regime import classify_market_regime
from app.models import DailyCandidateScan, Prediction, ScanCandidate, Stock
from app.recommendation_alerts import (
    ALERT_TYPE_EXPIRY,
    ALERT_TYPE_INVALIDATION,
    ALERT_TYPE_MARKET_REGIME_CHANGE,
    ALERT_TYPE_NEW_OPPORTUNITY,
    ALERT_TYPE_REVALIDATION_UPDATE,
    RecommendationAlertImmutableError,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    create_alert_from_new_opportunity,
    create_alert_from_regime_change,
    create_alert_from_revalidation,
    get_alert_history,
    set_alert_preference,
)
from app.recommendation_revalidation import revalidate_recommendation
from app.recommendation_selection import select_recommendations_for_scan
from app.recommendation_tracking import record_daily_observations
from app.target_stop_loss import publish_recommendation

AS_OF = datetime(2026, 12, 1, tzinfo=timezone.utc)
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


def _make_scan(session, *, eligible_count=1):
    scan_date = AS_OF.date() + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=eligible_count, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_prediction(session, scan, symbol, *, atr_percent=Decimal("0.001"), sma20_distance=Decimal("0.03"), strong=True):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.95") if strong else Decimal("0.72"),
        confidence=Decimal("0.90") if strong else Decimal("0.80"),
        sma20_distance=sma20_distance, volume_ratio_20d=Decimal("1.80") if strong else Decimal("1.10"),
        atr_percent=atr_percent, data_quality_passed=True, model_version="test-model-1", feature_version="FV-001",
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


def test_no_alert_for_unchanged_revalidation(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA")
    from app.models import MarketPrice
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("101"), high=Decimal("102"), low=Decimal("100"), close=Decimal("101"),
        volume=1000, source="test",
    ))
    session.flush()
    record_daily_observations(session, prediction)
    outcome = revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))

    alert = create_alert_from_revalidation(session, user_id="user-1", revalidation_outcome=outcome, triggered_at=AS_OF + timedelta(days=1))

    assert alert is None
    assert get_alert_history(session, "user-1") == ()


def test_expiry_alert_has_low_severity(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA", atr_percent=Decimal("0.035"))  # horizon=1
    from app.models import MarketPrice
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("101"), high=Decimal("102"), low=Decimal("100"), close=Decimal("101"),
        volume=1000, source="test",
    ))
    session.flush()
    record_daily_observations(session, prediction)
    outcome = revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))

    alert = create_alert_from_revalidation(session, user_id="user-2", revalidation_outcome=outcome, triggered_at=AS_OF + timedelta(days=1))

    assert alert.alert_type == ALERT_TYPE_EXPIRY
    assert alert.severity == SEVERITY_LOW


def test_withdrawn_alert_has_high_severity(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA")
    from app.models import MarketPrice
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("97.2"), high=Decimal("98"), low=Decimal("97"), close=Decimal("97.2"),
        volume=1000, source="test",
    ))
    session.flush()
    record_daily_observations(session, prediction)
    outcome = revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))

    alert = create_alert_from_revalidation(session, user_id="user-3", revalidation_outcome=outcome, triggered_at=AS_OF + timedelta(days=1))

    assert alert.alert_type == ALERT_TYPE_INVALIDATION
    assert alert.severity == SEVERITY_HIGH


def test_duplicate_alerts_are_suppressed(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA")
    from app.models import MarketPrice
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("104.6"), high=Decimal("105"), low=Decimal("104"), close=Decimal("104.6"),
        volume=1000, source="test",
    ))
    session.flush()
    record_daily_observations(session, prediction)
    outcome = revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))

    first = create_alert_from_revalidation(session, user_id="user-4", revalidation_outcome=outcome, triggered_at=AS_OF + timedelta(days=1))
    second = create_alert_from_revalidation(session, user_id="user-4", revalidation_outcome=outcome, triggered_at=AS_OF + timedelta(days=2))

    assert first.alert_type == ALERT_TYPE_REVALIDATION_UPDATE
    assert first.id == second.id
    assert len(get_alert_history(session, "user-4")) == 1


def test_muted_alert_type_is_suppressed(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA")
    from app.models import MarketPrice
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("97.2"), high=Decimal("98"), low=Decimal("97"), close=Decimal("97.2"),
        volume=1000, source="test",
    ))
    session.flush()
    record_daily_observations(session, prediction)
    outcome = revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))
    set_alert_preference(session, user_id="user-5", muted_alert_types=[ALERT_TYPE_INVALIDATION], effective_at=AS_OF)

    alert = create_alert_from_revalidation(session, user_id="user-5", revalidation_outcome=outcome, triggered_at=AS_OF + timedelta(days=1))

    assert alert is None


def test_market_regime_change_alert(session):
    scan_a = _make_scan(session)
    stock = Stock(symbol="BULL", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate_a = ScanCandidate(
        scan_id=scan_a.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.001"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate_a)
    session.flush()
    regime_a = classify_market_regime(session, scan_a.id)

    scan_b = _make_scan(session)
    candidate_b = ScanCandidate(
        scan_id=scan_b.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("-0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.001"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate_b)
    session.flush()
    regime_b = classify_market_regime(session, scan_b.id)
    assert regime_a.regime != regime_b.regime

    alert = create_alert_from_regime_change(session, user_id="user-6", previous_regime=regime_a, current_regime=regime_b, triggered_at=AS_OF)

    assert alert.alert_type == ALERT_TYPE_MARKET_REGIME_CHANGE
    assert alert.severity == SEVERITY_MEDIUM


def test_no_alert_for_unchanged_regime(session):
    scan = _make_scan(session)
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.001"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    regime = classify_market_regime(session, scan.id)

    alert = create_alert_from_regime_change(session, user_id="user-7", previous_regime=regime, current_regime=regime, triggered_at=AS_OF)

    assert alert is None


def test_new_opportunity_alert(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA", strong=True)
    selections = select_recommendations_for_scan(session, scan.id)
    selected = next(s for s in selections if s.selected)

    alert = create_alert_from_new_opportunity(session, user_id="user-8", selection=selected, triggered_at=AS_OF)

    assert alert.alert_type == ALERT_TYPE_NEW_OPPORTUNITY
    assert alert.prediction_id == prediction.id


def test_alert_is_immutable_after_creation(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA", strong=True)
    selections = select_recommendations_for_scan(session, scan.id)
    selected = next(s for s in selections if s.selected)
    alert = create_alert_from_new_opportunity(session, user_id="user-9", selection=selected, triggered_at=AS_OF)

    alert.severity = SEVERITY_LOW
    with pytest.raises(RecommendationAlertImmutableError, match="severity"):
        session.flush()
    session.rollback()


def test_no_alert_writes_to_prediction(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA")
    record_daily_observations(session, prediction)
    outcome = revalidate_recommendation(session, prediction, checked_at=AS_OF)
    before = (prediction.opportunity_score, prediction.status)

    create_alert_from_revalidation(session, user_id="user-10", revalidation_outcome=outcome, triggered_at=AS_OF)

    after = (prediction.opportunity_score, prediction.status)
    assert before == after
