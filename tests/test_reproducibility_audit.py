from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.consensus import CONTRACT_VERSION as CURRENT_CONSENSUS_VERSION
from app.db import Base
from app.decision_trace import capture_decision_trace
from app.discovery import SOURCE_CHATGPT, record_discovery, route_discovery_through_pipeline
from app.horizon import SELECTION_VERSION as CURRENT_HORIZON_SELECTION_VERSION
from app.models import DailyCandidateScan, MarketPrice, Prediction, RecommendationDecisionTrace, RecommendationGeneration, ScanCandidate, Stock
from app.reproducibility_audit import (
    AUDIT_RULE_VERSION,
    audit_prediction_reproducibility,
    get_reproducibility_audit_history,
)
from app.scoring import CONTRACT_VERSION as CURRENT_SCORING_VERSION
from app.target_stop_loss import TARGET_STOP_METHODOLOGY_VERSION as CURRENT_TARGET_STOP_VERSION

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)
_counter = iter(range(1000000))


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


def _make_qualified_generation(session):
    n = next(_counter)
    scan = DailyCandidateScan(scan_date=datetime(2027, 1, 1).date() + timedelta(days=n), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    stock = Stock(symbol=f"S{n}", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
        close=Decimal("100"), volume=1000, source="test",
    ))
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None, predicted_probability=Decimal("0.72"),
        confidence=Decimal("0.80"), sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("1.10"),
        atr_percent=Decimal("0.035"), data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    discovery = record_discovery(session, scan_id=scan.id, stock_id=stock.id, source=SOURCE_CHATGPT, rationale="t", discovered_at=AS_OF)
    generation = route_discovery_through_pipeline(
        session, discovery, as_of_timestamp=AS_OF, entry_price=Decimal("100"),
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
    )
    return generation


def test_reproducible_when_trace_matches_current_versions(session):
    generation = _make_qualified_generation(session)
    capture_decision_trace(session, generation, traced_at=AS_OF)
    prediction = session.get(Prediction, generation.prediction_id)

    decision = audit_prediction_reproducibility(session, prediction, audited_at=AS_OF)

    assert decision.reproducible is True
    assert decision.version_drifted_fields == []
    assert decision.audit_rule_version == AUDIT_RULE_VERSION


def test_no_trace_is_not_reproducible(session):
    n = next(_counter)
    stock = Stock(symbol=f"NT{n}", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=1,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.commit()

    decision = audit_prediction_reproducibility(session, prediction, audited_at=AS_OF)

    assert decision.reproducible is False


def _make_trace_with_versions(session, *, consensus_version, scoring_version, horizon_version, target_stop_version, sources):
    generation = _make_qualified_generation(session)
    prediction = session.get(Prediction, generation.prediction_id)
    session.add(RecommendationDecisionTrace(
        recommendation_generation_id=generation.id, prediction_id=prediction.id, stock_id=prediction.stock_id,
        as_of_timestamp=AS_OF, sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("1.1"), atr_percent=Decimal("0.02"),
        entry_price=Decimal("100"), horizon_days=1, target_return=Decimal("0.05"), stop_return=Decimal("-0.03"),
        predicted_probability=Decimal("0.7"), confidence=Decimal("0.8"), opportunity_score=Decimal("60.00"),
        model_version=MODEL_VERSION, feature_version="FV-001", consensus_contract_version=consensus_version,
        horizon_selection_version=horizon_version, scoring_contract_version=scoring_version,
        target_stop_methodology_version=target_stop_version, target_price=Decimal("105"), stop_loss_price=Decimal("97"),
        qualification_outcome="QUALIFIED", rejection_reasons=None,
        evidence_categories_snapshot=[{"category": "TECHNICAL_VOLUME", "status": "AVAILABLE", "source": s} for s in sources],
        traced_at=AS_OF, decision_trace_version="RDT-001",
    ))
    session.commit()
    return prediction


def test_version_drift_detected(session):
    prediction = _make_trace_with_versions(
        session, consensus_version="OLD-CONSENSUS", scoring_version=CURRENT_SCORING_VERSION,
        horizon_version=CURRENT_HORIZON_SELECTION_VERSION, target_stop_version=CURRENT_TARGET_STOP_VERSION,
        sources=["yahoo-finance"],
    )

    decision = audit_prediction_reproducibility(session, prediction, audited_at=AS_OF)

    assert decision.reproducible is False
    assert decision.version_drifted_fields == [
        {"field": "consensus_contract_version", "traced_value": "OLD-CONSENSUS", "current_value": CURRENT_CONSENSUS_VERSION}
    ]


def test_provider_drift_detected_when_checked(session):
    prediction = _make_trace_with_versions(
        session, consensus_version=CURRENT_CONSENSUS_VERSION, scoring_version=CURRENT_SCORING_VERSION,
        horizon_version=CURRENT_HORIZON_SELECTION_VERSION, target_stop_version=CURRENT_TARGET_STOP_VERSION,
        sources=["retired-provider"],
    )

    decision = audit_prediction_reproducibility(session, prediction, audited_at=AS_OF, currently_registered_provider_ids=("yahoo-finance", "alpha-vantage"))

    assert decision.reproducible is False
    assert decision.provider_drifted_categories == [{"category": "TECHNICAL_VOLUME", "traced_source": "retired-provider"}]


def test_provider_drift_not_checked_when_not_supplied(session):
    prediction = _make_trace_with_versions(
        session, consensus_version=CURRENT_CONSENSUS_VERSION, scoring_version=CURRENT_SCORING_VERSION,
        horizon_version=CURRENT_HORIZON_SELECTION_VERSION, target_stop_version=CURRENT_TARGET_STOP_VERSION,
        sources=["retired-provider"],
    )

    decision = audit_prediction_reproducibility(session, prediction, audited_at=AS_OF)

    assert decision.provider_drifted_categories == []
    assert decision.reproducible is True


def test_idempotent(session):
    generation = _make_qualified_generation(session)
    capture_decision_trace(session, generation, traced_at=AS_OF)
    prediction = session.get(Prediction, generation.prediction_id)

    first = audit_prediction_reproducibility(session, prediction, audited_at=AS_OF)
    second = audit_prediction_reproducibility(session, prediction, audited_at=AS_OF)

    assert first.id == second.id
    assert len(get_reproducibility_audit_history(session, prediction.id)) == 1
