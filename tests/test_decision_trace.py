from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.decision_trace import DECISION_TRACE_VERSION, capture_decision_trace, get_decision_trace
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_snapshot import capture_evidence_snapshot
from app.models import DailyCandidateScan, Prediction, ScanCandidate, Stock
from app.recommendation_generator import OUTCOME_NOT_QUALIFIED, OUTCOME_QUALIFIED
from app.target_stop_loss import publish_recommendation

AS_OF = datetime(2027, 1, 5, tzinfo=timezone.utc)
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


def _make_scan(session):
    scan_date = AS_OF.date() + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_qualified_generation(session, symbol="AAA"):
    scan = _make_scan(session)
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.72"), confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"),
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="strong setup", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return generation


def _make_rejected_generation(session, symbol="BBB"):
    scan = _make_scan(session)
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None,
        predicted_probability=Decimal("0.10"), confidence=Decimal("0.10"), sma20_distance=Decimal("-0.03"),
        volume_ratio_20d=Decimal("0.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="weak setup", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return generation


def test_qualified_trace_captures_full_decision(session):
    generation = _make_qualified_generation(session)
    assert generation.outcome == OUTCOME_QUALIFIED
    prediction = session.get(Prediction, generation.prediction_id)
    publish_recommendation(session, prediction, published_at=AS_OF)
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    trace = capture_decision_trace(session, generation, traced_at=AS_OF)

    assert trace.qualification_outcome == OUTCOME_QUALIFIED
    assert trace.prediction_id == prediction.id
    assert trace.model_version == "test-model-1"
    assert trace.opportunity_score == prediction.opportunity_score
    assert trace.target_price == Decimal("105.000000")
    assert trace.stop_loss_price == Decimal("97.000000")
    assert len(trace.evidence_categories_snapshot) == 5
    assert trace.rejection_reasons is None
    assert trace.decision_trace_version == DECISION_TRACE_VERSION


def test_rejected_trace_captures_rejection_reasons(session):
    generation = _make_rejected_generation(session)
    assert generation.outcome == OUTCOME_NOT_QUALIFIED

    trace = capture_decision_trace(session, generation, traced_at=AS_OF)

    assert trace.qualification_outcome == OUTCOME_NOT_QUALIFIED
    assert trace.prediction_id is None
    assert trace.rejection_reasons == generation.failed_criteria
    assert trace.rejection_reasons  # non-empty: at least one criterion failed
    assert trace.evidence_categories_snapshot == []


def test_trace_without_publication_or_evidence_yet_records_none_honestly(session):
    generation = _make_qualified_generation(session)
    # deliberately never calling publish_recommendation or capture_evidence_snapshot

    trace = capture_decision_trace(session, generation, traced_at=AS_OF)

    assert trace.target_price is None
    assert trace.stop_loss_price is None
    assert trace.evidence_categories_snapshot == []


def test_trace_is_idempotent(session):
    generation = _make_qualified_generation(session)

    first = capture_decision_trace(session, generation, traced_at=AS_OF)
    second = capture_decision_trace(session, generation, traced_at=AS_OF + timedelta(days=1))

    assert first.id == second.id
    assert get_decision_trace(session, generation.id).id == first.id


def test_trace_never_mutates_source_tables(session):
    generation = _make_qualified_generation(session)
    prediction = session.get(Prediction, generation.prediction_id)
    before = (prediction.opportunity_score, prediction.confidence, generation.outcome)

    capture_decision_trace(session, generation, traced_at=AS_OF)

    after = (prediction.opportunity_score, prediction.confidence, generation.outcome)
    assert before == after
