from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.evidence_quality_gate import (
    EVIDENCE_QUALITY_GATE_VERSION,
    MIN_AVAILABLE_CATEGORIES,
    REASON_FUTURE_DATED_EVIDENCE,
    REASON_NO_EVIDENCE_CAPTURED,
    REASON_TOO_FEW_AVAILABLE_CATEGORIES,
    STATE_INSUFFICIENT,
    STATE_LEAKAGE_DETECTED,
    STATE_SUFFICIENT,
    EvidenceQualityDecisionImmutableError,
    evaluate_evidence_quality,
    get_quality_decision_history,
)
from app.evidence_snapshot import (
    EVIDENCE_CATEGORY_NEWS,
    EVIDENCE_SNAPSHOT_VERSION,
    STATUS_AVAILABLE,
    capture_evidence_snapshot,
)
from app.models import DailyCandidateScan, MarketPrice, Prediction, RecommendationEvidenceItem, ScanCandidate, Stock
from app.recommendation_generator import generate_recommendation_for_candidate

AS_OF = datetime(2026, 9, 1, tzinfo=timezone.utc)
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
    scan_date = date(2026, 9, 1) + timedelta(days=next(_scan_counter))
    scan = DailyCandidateScan(scan_date=scan_date, universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    return scan


def _make_candidate(session, scan, symbol):
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
        volume_ratio_20d=Decimal("1.10"), atr_percent=Decimal("0.035"), data_quality_passed=True,
        model_version="test-model-1", feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    return stock, candidate


def _make_prediction_via_discovery(session, symbol):
    scan = _make_scan(session)
    stock, candidate = _make_candidate(session, scan, symbol)
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return session.get(Prediction, generation.prediction_id)


def _make_prediction_without_discovery(session, symbol):
    scan = _make_scan(session)
    stock, candidate = _make_candidate(session, scan, symbol)
    generation = generate_recommendation_for_candidate(
        session, candidate, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return session.get(Prediction, generation.prediction_id)


def test_no_evidence_captured_is_insufficient(session):
    prediction = _make_prediction_via_discovery(session, "AAA")

    decision = evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)

    assert decision.state == STATE_INSUFFICIENT
    assert REASON_NO_EVIDENCE_CAPTURED in decision.reasons
    assert decision.confidence_adjustment_ceiling == Decimal("0")
    assert decision.blocks_publication is True
    assert decision.gate_rule_version == EVIDENCE_QUALITY_GATE_VERSION


def test_meeting_the_minimum_available_categories_is_sufficient(session):
    prediction = _make_prediction_via_discovery(session, "BBB")
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    decision = evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)

    assert decision.available_category_count == MIN_AVAILABLE_CATEGORIES  # TECHNICAL_VOLUME + discovery-based NEWS
    assert decision.state == STATE_SUFFICIENT
    assert decision.reasons == []
    assert decision.confidence_adjustment_ceiling == prediction.confidence
    assert decision.blocks_publication is False


def test_below_minimum_available_categories_is_insufficient(session):
    prediction = _make_prediction_without_discovery(session, "CCC")
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    decision = evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)

    assert decision.available_category_count < MIN_AVAILABLE_CATEGORIES
    assert decision.state == STATE_INSUFFICIENT
    assert REASON_TOO_FEW_AVAILABLE_CATEGORIES in decision.reasons
    assert Decimal("0") < decision.confidence_adjustment_ceiling < prediction.confidence
    assert decision.blocks_publication is True


def test_future_dated_evidence_is_detected_as_leakage(session):
    prediction = _make_prediction_via_discovery(session, "DDD")
    # simulate a bug upstream: a category already "captured" with an
    # evidence_timestamp after the decision's own as_of_timestamp
    session.add(RecommendationEvidenceItem(
        prediction_id=prediction.id, evidence_category=EVIDENCE_CATEGORY_NEWS, status=STATUS_AVAILABLE,
        source="test-leak", reference="future news", evidence_timestamp=AS_OF + timedelta(days=10),
        is_stale=False, snapshot_rule_version=EVIDENCE_SNAPSHOT_VERSION, captured_at=AS_OF,
    ))
    session.commit()
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)  # fills remaining categories, leaves NEWS alone

    decision = evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)

    assert decision.state == STATE_LEAKAGE_DETECTED
    assert decision.leaked_categories == [EVIDENCE_CATEGORY_NEWS]
    assert REASON_FUTURE_DATED_EVIDENCE in decision.reasons
    assert decision.confidence_adjustment_ceiling == Decimal("0")
    assert decision.blocks_publication is True


def test_decision_is_idempotent_per_prediction_and_evaluated_at(session):
    prediction = _make_prediction_via_discovery(session, "EEE")
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    first = evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)
    second = evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)

    assert first.id == second.id
    assert len(get_quality_decision_history(session, prediction.id)) == 1


def test_a_later_evaluated_at_produces_a_new_row(session):
    prediction = _make_prediction_via_discovery(session, "FFF")
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)

    evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)
    evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF + timedelta(hours=1))

    assert len(get_quality_decision_history(session, prediction.id)) == 2


def test_decision_is_immutable(session):
    prediction = _make_prediction_via_discovery(session, "GGG")
    capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    decision = evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)

    decision.state = STATE_INSUFFICIENT
    with pytest.raises(EvidenceQualityDecisionImmutableError):
        session.commit()
    session.rollback()


def test_gate_never_writes_to_prediction_or_evidence_items(session):
    prediction = _make_prediction_via_discovery(session, "HHH")
    snapshot = capture_evidence_snapshot(session, prediction, captured_at=AS_OF)
    before_prediction = (prediction.confidence, prediction.opportunity_score)
    before_items = tuple((item.status, item.evidence_timestamp) for item in snapshot)

    evaluate_evidence_quality(session, prediction, evaluated_at=AS_OF)

    after_prediction = (prediction.confidence, prediction.opportunity_score)
    after_items = tuple((item.status, item.evidence_timestamp) for item in session.query(RecommendationEvidenceItem).filter_by(prediction_id=prediction.id).all())
    assert before_prediction == after_prediction
    assert set(before_items) == set(after_items)
