from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_revalidation import (
    EVIDENCE_REVALIDATION_VERSION,
    REASON_CHANGED,
    REASON_MISSING,
    REASON_STALE,
    EvidenceRevalidationImmutableError,
    get_revalidation_history,
    horizon_aware_threshold,
    revalidate_evidence,
)
from app.evidence_snapshot import EVIDENCE_CATEGORY_FUNDAMENTAL, EVIDENCE_CATEGORY_TECHNICAL_VOLUME, capture_evidence_snapshot
from app.models import DailyCandidateScan, MarketPrice, Prediction, RecommendationEvidenceItem, ScanCandidate, Stock

AS_OF = datetime(2026, 9, 10, tzinfo=timezone.utc)


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
    scan = DailyCandidateScan(scan_date=date(2026, 9, 10), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_prediction(session, scan, symbol, *, price_timestamp=None):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector="Energy")
    session.add(stock)
    session.flush()
    if price_timestamp is not None:
        session.add(MarketPrice(
            stock_id=stock.id, timestamp=price_timestamp,
            open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
            volume=1000, source="test",
        ))
        session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    return prediction, stock


def _technical_item(session, prediction):
    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    return next(i for i in snapshot if i.evidence_category == EVIDENCE_CATEGORY_TECHNICAL_VOLUME)


def test_horizon_aware_threshold_never_shrinks_below_the_base_policy(session):
    short = horizon_aware_threshold(EVIDENCE_CATEGORY_TECHNICAL_VOLUME, 1)
    long_ = horizon_aware_threshold(EVIDENCE_CATEGORY_TECHNICAL_VOLUME, 7)

    assert long_ > short
    assert short == timedelta(days=1)  # falls back to M1.35's base threshold


def test_fresh_evidence_requires_no_revalidation(session):
    scan = _make_scan(session)
    prediction, _stock = _make_prediction(session, scan, "AAA", price_timestamp=AS_OF)
    item = _technical_item(session, prediction)

    check = revalidate_evidence(session, prediction, item, checked_at=AS_OF)

    assert check.revalidation_required is False
    assert check.reason is None
    assert check.revalidation_rule_version == EVIDENCE_REVALIDATION_VERSION


def test_stale_evidence_triggers_revalidation(session):
    scan = _make_scan(session)
    prediction, _stock = _make_prediction(session, scan, "AAA", price_timestamp=AS_OF)
    item = _technical_item(session, prediction)

    much_later = AS_OF + timedelta(days=30)
    check = revalidate_evidence(session, prediction, item, checked_at=much_later)

    assert check.revalidation_required is True
    assert check.reason == REASON_STALE


def test_missing_evidence_triggers_revalidation(session):
    scan = _make_scan(session)
    prediction, _stock = _make_prediction(session, scan, "AAA")  # no MarketPrice at all
    item = _technical_item(session, prediction)
    assert item.evidence_timestamp is None

    check = revalidate_evidence(session, prediction, item, checked_at=AS_OF)

    assert check.revalidation_required is True
    assert check.reason == REASON_MISSING


def test_changed_evidence_triggers_revalidation(session):
    scan = _make_scan(session)
    prediction, stock = _make_prediction(session, scan, "AAA", price_timestamp=AS_OF)
    item = _technical_item(session, prediction)

    # new market data arrives after the snapshot was captured
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(hours=6),
        open=Decimal("101"), high=Decimal("102"), low=Decimal("100"), close=Decimal("101"),
        volume=1000, source="test",
    ))
    session.flush()

    check = revalidate_evidence(session, prediction, item, checked_at=AS_OF + timedelta(hours=12))

    assert check.revalidation_required is True
    assert check.reason == REASON_CHANGED
    assert check.current_value != check.original_value


def test_horizon_aware_threshold_tolerates_more_staleness_for_longer_horizons(session):
    scan = _make_scan(session)
    stock = Stock(symbol="LONGHZ", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF,
        open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        volume=1000, source="test",
    ))
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.001"), data_quality_passed=True,  # -> horizon=7
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    prediction = session.get(Prediction, generation.prediction_id)
    assert prediction.horizon_days == 7
    item = _technical_item(session, prediction)

    two_days_later = AS_OF + timedelta(days=2)
    check = revalidate_evidence(session, prediction, item, checked_at=two_days_later)

    # 2 days of staleness would exceed M1.35's flat 1-day threshold, but is
    # within the horizon-aware allowance for a 7-day horizon (3.5 days).
    assert check.revalidation_required is False
    assert check.reason is None


def test_revalidation_never_mutates_the_original_snapshot(session):
    scan = _make_scan(session)
    prediction, _stock = _make_prediction(session, scan, "AAA", price_timestamp=AS_OF)
    item = _technical_item(session, prediction)
    before = (item.status, item.reference, item.evidence_timestamp, item.is_stale)

    revalidate_evidence(session, prediction, item, checked_at=AS_OF + timedelta(days=30))

    refreshed = session.get(RecommendationEvidenceItem, item.id)
    after = (refreshed.status, refreshed.reference, refreshed.evidence_timestamp, refreshed.is_stale)
    assert before == after


def test_revalidation_check_is_immutable_after_creation(session):
    scan = _make_scan(session)
    prediction, _stock = _make_prediction(session, scan, "AAA", price_timestamp=AS_OF)
    item = _technical_item(session, prediction)
    check = revalidate_evidence(session, prediction, item, checked_at=AS_OF)

    check.revalidation_required = True
    with pytest.raises(EvidenceRevalidationImmutableError, match="revalidation_required"):
        session.flush()
    session.rollback()


def test_revalidation_history_retains_every_check(session):
    scan = _make_scan(session)
    prediction, _stock = _make_prediction(session, scan, "AAA", price_timestamp=AS_OF)
    item = _technical_item(session, prediction)

    revalidate_evidence(session, prediction, item, checked_at=AS_OF)
    revalidate_evidence(session, prediction, item, checked_at=AS_OF + timedelta(days=30))

    history = get_revalidation_history(session, prediction.id)
    assert len(history) == 2
    assert history[0].revalidation_required is False
    assert history[1].revalidation_required is True
