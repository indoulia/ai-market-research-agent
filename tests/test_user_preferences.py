from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.consensus import MIN_CONFIDENCE
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.models import DailyCandidateScan, Prediction, ScanCandidate, Stock
from app.recommendation_selection import select_recommendations_for_scan
from app.user_preferences import (
    DEFAULT_HORIZON_BAND,
    DEFAULT_RISK_PREFERENCE,
    HORIZON_BAND_CUSTOM,
    HORIZON_BAND_LONG,
    HORIZON_BAND_MEDIUM,
    HORIZON_BAND_SHORT,
    PREFERENCE_RULE_VERSION,
    REASON_BELOW_MIN_CONFIDENCE,
    REASON_NOT_IN_HORIZON_BAND,
    InvalidPreferenceError,
    UserPreferenceImmutableError,
    apply_preferences_to_scan_selection,
    get_current_preference,
    set_user_preference,
)

AS_OF = datetime(2026, 5, 10, tzinfo=timezone.utc)


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
    scan = DailyCandidateScan(scan_date=date(2026, 5, 10), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_qualified(session, scan, symbol, *, sector="Energy", market_cap=Decimal("30000"), confidence=Decimal("0.80")):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector=sector, market_cap=market_cap)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.95"), confidence=confidence, sma20_distance=Decimal("0.08"),
        volume_ratio_20d=Decimal("1.80"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return generation


def test_new_user_defaults_to_short_term(session):
    preference = get_current_preference(session, "user-1", effective_at=AS_OF)

    assert preference.horizon_band == DEFAULT_HORIZON_BAND
    assert preference.horizon_band == HORIZON_BAND_SHORT
    assert preference.risk_preference == DEFAULT_RISK_PREFERENCE
    assert preference.min_confidence_threshold == MIN_CONFIDENCE
    assert preference.preference_rule_version == PREFERENCE_RULE_VERSION


def test_get_current_preference_is_idempotent_for_a_new_user(session):
    first = get_current_preference(session, "user-1", effective_at=AS_OF)
    second = get_current_preference(session, "user-1", effective_at=AS_OF)

    assert first.id == second.id


def test_a_user_can_change_preferences_without_mutating_the_prior_version(session):
    first = set_user_preference(session, user_id="user-1", effective_at=AS_OF, horizon_band=HORIZON_BAND_SHORT)
    second = set_user_preference(session, user_id="user-1", effective_at=AS_OF + timedelta(days=1), horizon_band=HORIZON_BAND_MEDIUM)

    assert first.id != second.id
    assert first.horizon_band == HORIZON_BAND_SHORT
    current = get_current_preference(session, "user-1", effective_at=AS_OF + timedelta(days=2))
    assert current.id == second.id
    assert current.horizon_band == HORIZON_BAND_MEDIUM


def test_custom_horizon_requires_a_valid_day_count(session):
    with pytest.raises(InvalidPreferenceError):
        set_user_preference(session, user_id="user-1", effective_at=AS_OF, horizon_band=HORIZON_BAND_CUSTOM, custom_horizon_days=None)

    with pytest.raises(InvalidPreferenceError):
        set_user_preference(session, user_id="user-1", effective_at=AS_OF, horizon_band=HORIZON_BAND_CUSTOM, custom_horizon_days=4)

    preference = set_user_preference(session, user_id="user-1", effective_at=AS_OF, horizon_band=HORIZON_BAND_CUSTOM, custom_horizon_days=3)
    assert preference.custom_horizon_days == 3


def test_custom_horizon_days_rejected_for_non_custom_band(session):
    with pytest.raises(InvalidPreferenceError):
        set_user_preference(session, user_id="user-1", effective_at=AS_OF, horizon_band=HORIZON_BAND_SHORT, custom_horizon_days=3)


def test_invalid_risk_preference_is_rejected(session):
    with pytest.raises(InvalidPreferenceError):
        set_user_preference(session, user_id="user-1", effective_at=AS_OF, risk_preference="EXTREME")


def test_invalid_confidence_threshold_is_rejected(session):
    with pytest.raises(InvalidPreferenceError):
        set_user_preference(session, user_id="user-1", effective_at=AS_OF, min_confidence_threshold=Decimal("1.5"))


def test_invalid_market_cap_bucket_is_rejected(session):
    with pytest.raises(InvalidPreferenceError):
        set_user_preference(session, user_id="user-1", effective_at=AS_OF, preferred_market_cap_buckets=["GALACTIC_CAP"])


def test_preference_is_immutable_after_creation(session):
    preference = set_user_preference(session, user_id="user-1", effective_at=AS_OF)

    preference.horizon_band = HORIZON_BAND_LONG
    with pytest.raises(UserPreferenceImmutableError, match="horizon_band"):
        session.flush()
    session.rollback()


def test_recommendation_within_preferences_is_included(session):
    scan = _make_scan(session)
    _make_qualified(session, scan, "AAA")
    select_recommendations_for_scan(session, scan.id)

    snapshots = apply_preferences_to_scan_selection(session, user_id="user-1", scan_id=scan.id, snapshotted_at=AS_OF)

    assert len(snapshots) == 1
    assert snapshots[0].included is True
    assert snapshots[0].exclusion_reason is None
    assert snapshots[0].matched_horizon is True
    assert snapshots[0].met_min_confidence is True


def test_recommendation_outside_horizon_band_is_excluded(session):
    scan = _make_scan(session)
    _make_qualified(session, scan, "AAA")
    select_recommendations_for_scan(session, scan.id)
    set_user_preference(session, user_id="user-2", effective_at=AS_OF, horizon_band=HORIZON_BAND_MEDIUM)

    snapshots = apply_preferences_to_scan_selection(session, user_id="user-2", scan_id=scan.id, snapshotted_at=AS_OF)

    assert snapshots[0].included is False
    assert snapshots[0].exclusion_reason == REASON_NOT_IN_HORIZON_BAND


def test_recommendation_below_min_confidence_preference_is_excluded(session):
    scan = _make_scan(session)
    _make_qualified(session, scan, "AAA", confidence=Decimal("0.60"))
    select_recommendations_for_scan(session, scan.id)
    set_user_preference(session, user_id="user-3", effective_at=AS_OF, min_confidence_threshold=Decimal("0.75"))

    snapshots = apply_preferences_to_scan_selection(session, user_id="user-3", scan_id=scan.id, snapshotted_at=AS_OF)

    assert snapshots[0].included is False
    assert snapshots[0].exclusion_reason == REASON_BELOW_MIN_CONFIDENCE


def test_preferred_sector_produces_a_soft_match_boost_without_excluding_others(session):
    scan = _make_scan(session)
    _make_qualified(session, scan, "ENERGY_STOCK", sector="Energy")
    _make_qualified(session, scan, "TECH_STOCK", sector="Technology")
    select_recommendations_for_scan(session, scan.id)
    set_user_preference(session, user_id="user-4", effective_at=AS_OF, preferred_sectors=["Energy"])

    snapshots = apply_preferences_to_scan_selection(session, user_id="user-4", scan_id=scan.id, snapshotted_at=AS_OF)

    by_boost = {s.preference_match_boost for s in snapshots}
    assert by_boost == {True, False}
    assert all(s.included for s in snapshots)


def test_preference_change_does_not_mutate_an_existing_snapshot(session):
    scan = _make_scan(session)
    _make_qualified(session, scan, "AAA")
    select_recommendations_for_scan(session, scan.id)
    first = apply_preferences_to_scan_selection(session, user_id="user-5", scan_id=scan.id, snapshotted_at=AS_OF)

    set_user_preference(session, user_id="user-5", effective_at=AS_OF + timedelta(days=1), horizon_band=HORIZON_BAND_LONG)
    second = apply_preferences_to_scan_selection(session, user_id="user-5", scan_id=scan.id, snapshotted_at=AS_OF + timedelta(days=1))

    assert first[0].id == second[0].id
    assert second[0].horizon_band == HORIZON_BAND_SHORT  # the original snapshot's preference, not the new one


def test_snapshot_never_touches_prediction_or_scan_candidate(session):
    scan = _make_scan(session)
    _make_qualified(session, scan, "AAA")
    select_recommendations_for_scan(session, scan.id)
    before_predictions = {p.id: (p.opportunity_score, p.horizon_days) for p in session.query(Prediction).all()}
    before_candidates = {c.id: c.confidence for c in session.query(ScanCandidate).all()}

    apply_preferences_to_scan_selection(session, user_id="user-6", scan_id=scan.id, snapshotted_at=AS_OF)

    after_predictions = {p.id: (p.opportunity_score, p.horizon_days) for p in session.query(Prediction).all()}
    after_candidates = {c.id: c.confidence for c in session.query(ScanCandidate).all()}
    assert before_predictions == after_predictions
    assert before_candidates == after_candidates
