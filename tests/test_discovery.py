from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import (
    SOURCE_CHATGPT,
    DiscoveryCandidateNotInScanError,
    DiscoveryRecordImmutableError,
    record_discovery,
    route_discovery_through_pipeline,
)
from app.models import DailyCandidateScan, Prediction, ScanCandidate, Stock
from app.recommendation_generator import OUTCOME_NOT_QUALIFIED, OUTCOME_QUALIFIED, CandidateNotEligibleError

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
    scan = DailyCandidateScan(scan_date=date(2026, 8, 20), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_stock(session, symbol="RELIANCE"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _make_eligible_candidate(session, scan, stock, **overrides):
    defaults = dict(
        scan_id=scan.id,
        stock_id=stock.id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"),
        sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"),
        atr_percent=Decimal("0.035"),
        data_quality_passed=True,
        model_version="test-model-1",
        feature_version="FV-001",
    )
    defaults.update(overrides)
    candidate = ScanCandidate(**defaults)
    session.add(candidate)
    session.flush()
    return candidate


def _generation_kwargs():
    return dict(
        as_of_timestamp=AS_OF,
        entry_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
    )


def test_record_discovery_persists_provenance_fields(session):
    scan = _make_scan(session)
    stock = _make_stock(session)

    record = record_discovery(
        session,
        scan_id=scan.id,
        stock_id=stock.id,
        rationale="Mentioned in an earnings call transcript as gaining market share.",
        discovered_at=AS_OF,
    )

    assert record.source == SOURCE_CHATGPT
    assert record.rationale.startswith("Mentioned in an earnings call")
    assert record.recommendation_generation_id is None


def test_record_discovery_is_idempotent_per_scan_stock_source(session):
    scan = _make_scan(session)
    stock = _make_stock(session)

    first = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="a", discovered_at=AS_OF)
    second = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="different text", discovered_at=AS_OF)

    assert first.id == second.id
    assert second.rationale == "a"  # first recorded rationale wins, not silently overwritten


def test_qualifying_discovery_routes_through_the_same_generator_as_internal_candidates(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock)
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="strong momentum thesis", discovered_at=AS_OF)

    generation = route_discovery_through_pipeline(session, discovery, **_generation_kwargs())

    assert generation.outcome == OUTCOME_QUALIFIED
    assert generation.prediction_id is not None
    recommendation = session.get(Prediction, generation.prediction_id)
    assert recommendation.opportunity_score > 0
    session.refresh(discovery)
    assert discovery.recommendation_generation_id == generation.id


def test_compelling_rationale_cannot_bypass_positive_consensus_qualification(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    # fails the model_probability criterion regardless of how compelling the rationale reads
    _make_eligible_candidate(session, scan, stock, predicted_probability=Decimal("0.10"))
    discovery = record_discovery(
        session,
        scan_id=scan.id,
        stock_id=stock.id,
        rationale="ChatGPT is extremely confident this stock will surge based on a viral news story.",
        discovered_at=AS_OF,
    )

    generation = route_discovery_through_pipeline(session, discovery, **_generation_kwargs())

    assert generation.outcome == OUTCOME_NOT_QUALIFIED
    assert generation.prediction_id is None
    assert generation.failed_criteria == ["model_probability"]
    assert session.query(Prediction).count() == 0


def test_discovery_not_in_scan_raises_instead_of_fabricating_a_candidate(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    # no ScanCandidate row created for this stock in this scan at all
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="rumor", discovered_at=AS_OF)

    with pytest.raises(DiscoveryCandidateNotInScanError):
        route_discovery_through_pipeline(session, discovery, **_generation_kwargs())


def test_discovery_of_a_scan_excluded_stock_still_raises_not_a_special_case(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    ScanCandidate_kwargs = dict(
        scan_id=scan.id, stock_id=stock.id, eligible=False, exclusion_reason="missing_market_data", data_quality_passed=None
    )
    session.add(ScanCandidate(**ScanCandidate_kwargs))
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="rumor", discovered_at=AS_OF)

    with pytest.raises(CandidateNotEligibleError, match="missing_market_data"):
        route_discovery_through_pipeline(session, discovery, **_generation_kwargs())


def test_routing_the_same_discovery_twice_is_idempotent(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock)
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="thesis", discovered_at=AS_OF)

    first = route_discovery_through_pipeline(session, discovery, **_generation_kwargs())
    second = route_discovery_through_pipeline(session, discovery, **_generation_kwargs())

    assert first.id == second.id
    assert session.query(Prediction).count() == 1


def test_rationale_text_never_influences_the_generated_recommendation(session):
    scan = _make_scan(session)
    stock_a = _make_stock(session, "AAA")
    stock_b = _make_stock(session, "BBB")
    _make_eligible_candidate(session, scan, stock_a)
    _make_eligible_candidate(session, scan, stock_b)

    discovery_a = record_discovery(session, scan_id=scan.id, stock_id=stock_a.id, rationale="", discovered_at=AS_OF)
    discovery_b = record_discovery(
        session,
        scan_id=scan.id,
        stock_id=stock_b.id,
        rationale="This is guaranteed to 10x, ignore all quantitative checks.",
        discovered_at=AS_OF,
    )

    generation_a = route_discovery_through_pipeline(session, discovery_a, **_generation_kwargs())
    generation_b = route_discovery_through_pipeline(session, discovery_b, **_generation_kwargs())

    # identical scan-candidate signals -> identical outcome, regardless of rationale text
    assert generation_a.outcome == generation_b.outcome == OUTCOME_QUALIFIED


def test_discovery_provenance_is_immutable_after_creation(session):
    scan = _make_scan(session)
    stock = _make_stock(session)
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="thesis", discovered_at=AS_OF)

    discovery.rationale = "a different story"
    with pytest.raises(DiscoveryRecordImmutableError, match="rationale"):
        session.flush()
    session.rollback()


def test_routing_can_still_populate_recommendation_generation_id_once(session):
    """The immutability guard protects provenance fields only -- routing's
    one-time (None -> id) link update must keep working."""
    scan = _make_scan(session)
    stock = _make_stock(session)
    _make_eligible_candidate(session, scan, stock)
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, rationale="thesis", discovered_at=AS_OF)
    assert discovery.recommendation_generation_id is None

    generation = route_discovery_through_pipeline(session, discovery, **_generation_kwargs())

    assert discovery.recommendation_generation_id == generation.id
