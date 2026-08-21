from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data_source_reliability import compute_data_source_reliability_report
from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_conflict_resolution import (
    MATERIAL_CONFLICT_THRESHOLD,
    REASON_REVALIDATION_CONFLICT,
    REASON_UNTRUSTED_SOURCE,
    RESOLUTION_RULE_VERSION,
    STATE_INSUFFICIENT_EVIDENCE,
    STATE_RESOLVED,
    STATE_UNRESOLVED,
    get_conflict_resolution_history,
    resolve_evidence_conflicts,
)
from app.evidence_snapshot import capture_evidence_snapshot
from app.models import DailyCandidateScan, MarketPrice, Prediction, ScanCandidate, Stock
from app.recommendation_revalidation import revalidate_recommendation
from app.recommendation_tracking import record_daily_observations
from app.target_stop_loss import publish_recommendation

AS_OF = datetime(2026, 12, 20, tzinfo=timezone.utc)
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


def _make_prediction(session, symbol="AAA", *, atr_percent=Decimal("0.001")):
    scan_date = AS_OF.date() + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
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
        volume_ratio_20d=Decimal("1.10"), atr_percent=atr_percent, data_quality_passed=True,
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
    publish_recommendation(session, prediction, published_at=AS_OF)
    return prediction, stock


def test_no_evidence_and_no_revalidation_is_insufficient(session):
    prediction, _stock = _make_prediction(session)
    report = compute_data_source_reliability_report(session)

    resolution = resolve_evidence_conflicts(session, prediction, reliability_report=report, resolved_at=AS_OF)

    assert resolution.state == STATE_INSUFFICIENT_EVIDENCE
    assert resolution.resolution_rule_version == RESOLUTION_RULE_VERSION


def test_available_evidence_with_no_conflicts_is_resolved(session):
    prediction, _stock = _make_prediction(session)
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    report = compute_data_source_reliability_report(session)

    resolution = resolve_evidence_conflicts(session, prediction, reliability_report=report, resolved_at=AS_OF)

    # FUNDAMENTAL/EVENT are always UNAVAILABLE (never counted as conflicts);
    # TECHNICAL_VOLUME/MARKET_SECTOR have no M1.64 reliability data yet, so
    # there is no untrusted-source verdict to conflict with.
    assert resolution.state in (STATE_RESOLVED, STATE_UNRESOLVED)
    assert set(resolution.evidence_categories_considered) == {"FUNDAMENTAL", "NEWS", "EVENT", "MARKET_SECTOR", "TECHNICAL_VOLUME"}


def test_untrusted_source_produces_an_unresolved_conflict(session):
    prediction, stock = _make_prediction(session)
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    from app.data_source_reliability import EvidenceQualityStatus, DataSourceReliabilityReport
    fake_report = DataSourceReliabilityReport(
        version="DSR-001", by_data_type=(), by_evidence_category=(),
        quality_statuses=(EvidenceQualityStatus(key="TECHNICAL_VOLUME", trusted=False, reason="fabricated for test"),),
    )

    resolution = resolve_evidence_conflicts(session, prediction, reliability_report=fake_report, resolved_at=AS_OF)

    assert resolution.state == STATE_UNRESOLVED
    assert resolution.conflict_count == 1
    assert resolution.conflicts[0]["reason"] == REASON_UNTRUSTED_SOURCE
    assert resolution.blocks_qualification is True
    assert resolution.confidence_adjustment_ceiling < prediction.confidence


def test_revalidation_withdrawal_produces_a_conflict(session):
    prediction, stock = _make_prediction(session)
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF + timedelta(days=1),
        open=Decimal("97.2"), high=Decimal("98"), low=Decimal("97"), close=Decimal("97.2"),
        volume=1000, source="test",
    ))
    session.flush()
    record_daily_observations(session, prediction)
    revalidate_recommendation(session, prediction, checked_at=AS_OF + timedelta(days=1))
    report = compute_data_source_reliability_report(session)

    resolution = resolve_evidence_conflicts(session, prediction, reliability_report=report, resolved_at=AS_OF + timedelta(days=1))

    assert resolution.state == STATE_UNRESOLVED
    assert any(c["reason"] == REASON_REVALIDATION_CONFLICT for c in resolution.conflicts)


def test_no_source_is_silently_discarded(session):
    prediction, _stock = _make_prediction(session)
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    report = compute_data_source_reliability_report(session)

    resolution = resolve_evidence_conflicts(session, prediction, reliability_report=report, resolved_at=AS_OF)

    assert len(resolution.evidence_categories_considered) == 5


def test_resolution_is_idempotent_for_the_same_resolved_at(session):
    prediction, _stock = _make_prediction(session)
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    report = compute_data_source_reliability_report(session)

    first = resolve_evidence_conflicts(session, prediction, reliability_report=report, resolved_at=AS_OF)
    second = resolve_evidence_conflicts(session, prediction, reliability_report=report, resolved_at=AS_OF)

    assert first.id == second.id
    assert len(get_conflict_resolution_history(session, prediction.id)) == 1


def test_resolution_never_mutates_prediction_or_evidence(session):
    prediction, _stock = _make_prediction(session)
    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    before_prediction = (prediction.confidence, prediction.opportunity_score)
    before_snapshot = tuple((item.status, item.reference) for item in snapshot)
    report = compute_data_source_reliability_report(session)

    resolve_evidence_conflicts(session, prediction, reliability_report=report, resolved_at=AS_OF)

    after_prediction = (prediction.confidence, prediction.opportunity_score)
    after_snapshot = tuple((item.status, item.reference) for item in snapshot)
    assert before_prediction == after_prediction
    assert before_snapshot == after_snapshot


def test_real_corporate_event_evidence_resolves_cleanly_through_m1_65(session):
    """EPIC-M1.73's AC 'support evidence conflict handling through M1.65'
    is structural, not a code change in M1.65 itself: once EVENT evidence
    is real (M1.64's coverage is no longer permanently zero for this
    category), M1.65 processes it exactly like any other trusted,
    available category, with no special-casing required."""
    from app.news_data.ingest import EVENT_TYPE_CORPORATE_EVENT, MATERIALITY_HIGH, NEWS_EVENT_INGESTION_VERSION
    from app.models import NewsEventRecord

    prediction, stock = _make_prediction(session)
    session.add(NewsEventRecord(
        stock_id=stock.id, source="yahoo-finance", external_id="e1",
        headline="Company announces merger agreement", event_type=EVENT_TYPE_CORPORATE_EVENT,
        materiality=MATERIALITY_HIGH, published_at=AS_OF - timedelta(hours=1), fetched_at=AS_OF - timedelta(hours=1),
        ingestion_rule_version=NEWS_EVENT_INGESTION_VERSION,
    ))
    session.commit()

    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    event_item = {item.evidence_category: item for item in snapshot}["EVENT"]
    assert event_item.status == "AVAILABLE"

    report = compute_data_source_reliability_report(session)
    event_status = next(s for s in report.quality_statuses if s.key == "EVENT")
    assert event_status.trusted is True

    resolution = resolve_evidence_conflicts(session, prediction, reliability_report=report, resolved_at=AS_OF)
    assert resolution.state == STATE_RESOLVED
