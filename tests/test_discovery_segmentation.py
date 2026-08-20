from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import record_discovery
from app.discovery_segmentation import (
    BUCKET_UNCLASSIFIED,
    SEGMENTATION_VERSION,
    DiscoverySegmentImmutableError,
    classify_liquidity_bucket,
    classify_market_cap_bucket,
    discovery_records_in_segment,
    over_concentrated_segments,
    record_segment_for_discovery,
    record_segments_for_scan,
    segment_coverage_for_scan,
)
from app.models import DailyCandidateScan, ScanCandidate, Stock

AS_OF = datetime(2026, 8, 20, tzinfo=timezone.utc)


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


def _make_stock(session, symbol, *, sector=None, industry=None, market_cap=None):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True, sector=sector, industry=industry, market_cap=market_cap)
    session.add(stock)
    session.flush()
    return stock


def _make_candidate(session, scan, stock, *, volume_ratio_20d=None, eligible=True):
    candidate = ScanCandidate(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=eligible,
        exclusion_reason=None if eligible else "missing_market_data",
        volume_ratio_20d=volume_ratio_20d,
        data_quality_passed=eligible,
    )
    session.add(candidate)
    session.flush()
    return candidate


def test_classify_market_cap_bucket_boundaries():
    assert classify_market_cap_bucket(None) == BUCKET_UNCLASSIFIED
    assert classify_market_cap_bucket(Decimal("20000")) == "LARGE_CAP"
    assert classify_market_cap_bucket(Decimal("19999.99")) == "MID_CAP"
    assert classify_market_cap_bucket(Decimal("5000")) == "MID_CAP"
    assert classify_market_cap_bucket(Decimal("4999.99")) == "SMALL_CAP"
    assert classify_market_cap_bucket(Decimal("0")) == "SMALL_CAP"


def test_classify_liquidity_bucket_boundaries():
    assert classify_liquidity_bucket(None) == BUCKET_UNCLASSIFIED
    assert classify_liquidity_bucket(Decimal("1.5")) == "HIGH"
    assert classify_liquidity_bucket(Decimal("1.49")) == "NORMAL"
    assert classify_liquidity_bucket(Decimal("0.75")) == "NORMAL"
    assert classify_liquidity_bucket(Decimal("0.74")) == "LOW"


def test_record_segment_snapshots_stock_and_candidate_metadata(session):
    scan = _make_scan(session)
    stock = _make_stock(session, "RELIANCE", sector="Energy", industry="Oil & Gas", market_cap=Decimal("150000"))
    candidate = _make_candidate(session, scan, stock, volume_ratio_20d=Decimal("2.0"))
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="scan", discovered_at=AS_OF)

    segment = record_segment_for_discovery(session, discovery, stock, candidate)

    assert segment.market_cap_bucket == "LARGE_CAP"
    assert segment.sector == "Energy"
    assert segment.industry == "Oil & Gas"
    assert segment.liquidity_bucket == "HIGH"
    assert segment.segmentation_rule_version == SEGMENTATION_VERSION


def test_missing_metadata_is_recorded_as_unclassified_not_omitted(session):
    scan = _make_scan(session)
    stock = _make_stock(session, "UNKNOWNCO")
    candidate = _make_candidate(session, scan, stock, volume_ratio_20d=None)
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="scan", discovered_at=AS_OF)

    segment = record_segment_for_discovery(session, discovery, stock, candidate)

    assert segment.market_cap_bucket == BUCKET_UNCLASSIFIED
    assert segment.sector == BUCKET_UNCLASSIFIED
    assert segment.industry == BUCKET_UNCLASSIFIED
    assert segment.liquidity_bucket == BUCKET_UNCLASSIFIED


def test_recording_segment_twice_is_idempotent_and_keeps_the_original_snapshot(session):
    scan = _make_scan(session)
    stock = _make_stock(session, "RELIANCE", sector="Energy", market_cap=Decimal("150000"))
    candidate = _make_candidate(session, scan, stock, volume_ratio_20d=Decimal("2.0"))
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="scan", discovered_at=AS_OF)

    first = record_segment_for_discovery(session, discovery, stock, candidate)
    stock.market_cap = Decimal("1000")  # stock reclassified later; must not rewrite history
    session.flush()
    second = record_segment_for_discovery(session, discovery, stock, candidate)

    assert first.id == second.id
    assert second.market_cap_bucket == "LARGE_CAP"  # original snapshot, not the later reclassification


def test_segment_is_immutable_after_creation(session):
    scan = _make_scan(session)
    stock = _make_stock(session, "RELIANCE", sector="Energy", market_cap=Decimal("150000"))
    candidate = _make_candidate(session, scan, stock, volume_ratio_20d=Decimal("2.0"))
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="scan", discovered_at=AS_OF)
    segment = record_segment_for_discovery(session, discovery, stock, candidate)

    segment.sector = "Technology"
    with pytest.raises(DiscoverySegmentImmutableError, match="sector"):
        session.flush()
    session.rollback()


def test_record_segments_for_scan_covers_every_discovery_record(session):
    scan = _make_scan(session)
    energy = _make_stock(session, "ENERGY1", sector="Energy", market_cap=Decimal("30000"))
    tech = _make_stock(session, "TECH1", sector="Technology", market_cap=Decimal("2000"))
    _make_candidate(session, scan, energy, volume_ratio_20d=Decimal("1.0"))
    _make_candidate(session, scan, tech, volume_ratio_20d=Decimal("0.5"))
    record_discovery(session, scan_id=scan.id, stock_id=energy.id, rationale="scan", discovered_at=AS_OF)
    record_discovery(session, scan_id=scan.id, stock_id=tech.id, rationale="scan", discovered_at=AS_OF)

    segments = record_segments_for_scan(session, scan.id)

    assert len(segments) == 2
    by_sector = {s.sector for s in segments}
    assert by_sector == {"Energy", "Technology"}


def test_segment_coverage_and_over_concentration_detection(session):
    scan = _make_scan(session)
    for i in range(8):
        stock = _make_stock(session, f"ENERGY{i}", sector="Energy", market_cap=Decimal("30000"))
        _make_candidate(session, scan, stock, volume_ratio_20d=Decimal("1.0"))
        record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="scan", discovered_at=AS_OF)
    for i in range(2):
        stock = _make_stock(session, f"TECH{i}", sector="Technology", market_cap=Decimal("2000"))
        _make_candidate(session, scan, stock, volume_ratio_20d=Decimal("0.5"))
        record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="scan", discovered_at=AS_OF)
    record_segments_for_scan(session, scan.id)

    coverage = segment_coverage_for_scan(session, scan.id)

    assert coverage.total == 10
    assert coverage.by_sector["Energy"] == 8
    assert coverage.by_sector["Technology"] == 2
    flagged = over_concentrated_segments(coverage.by_sector, coverage.total)
    assert flagged == ("Energy",)


def test_discovery_records_in_segment_filters_a_single_run(session):
    scan = _make_scan(session)
    energy = _make_stock(session, "ENERGY1", sector="Energy", market_cap=Decimal("30000"))
    tech = _make_stock(session, "TECH1", sector="Technology", market_cap=Decimal("2000"))
    _make_candidate(session, scan, energy, volume_ratio_20d=Decimal("1.0"))
    _make_candidate(session, scan, tech, volume_ratio_20d=Decimal("0.5"))
    record_discovery(session, scan_id=scan.id, stock_id=energy.id, rationale="scan", discovered_at=AS_OF)
    record_discovery(session, scan_id=scan.id, stock_id=tech.id, rationale="scan", discovered_at=AS_OF)
    record_segments_for_scan(session, scan.id)

    energy_only = discovery_records_in_segment(session, scan.id, sector="Energy")

    assert len(energy_only) == 1
    assert energy_only[0].stock_id == energy.id
