from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.feature_drift_monitor import FEATURE_SMA20_DISTANCE
from app.models import FeatureDriftAssessment, FundamentalConsensusAssessment, MarketPrice, Prediction, Stock
from app.prediction_freshness_engine import (
    FRESHNESS_ENGINE_VERSION,
    TRIGGER_COVERAGE_DRIFT_DETECTED,
    TRIGGER_FEATURE_DRIFT_DETECTED,
    TRIGGER_FUNDAMENTAL_PROVIDER_DISAGREEMENT,
    TRIGGER_REVALIDATION_MATERIAL_CHANGE,
    evaluate_prediction_freshness,
    get_freshness_history,
)
from app.recommendation_revalidation import OUTCOME_UNCHANGED
from app.recommendation_revision import REASON_MATERIAL_EVIDENCE_CHANGE

MODEL_VERSION = "test-model-1"
AS_OF = datetime(2027, 1, 1, tzinfo=timezone.utc)


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


def _make_prediction(session, *, with_fresh_market_data=True):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    if with_fresh_market_data:
        session.add(MarketPrice(
            stock_id=stock.id, timestamp=AS_OF, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
            close=Decimal("100"), volume=1000, source="test",
        ))
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=5,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"),
    )
    session.add(prediction)
    session.commit()
    return prediction


def test_no_triggers_when_everything_clean(session):
    prediction = _make_prediction(session)

    decision = evaluate_prediction_freshness(session, prediction, evaluated_at=AS_OF)

    assert decision.revalidation_outcome == OUTCOME_UNCHANGED
    assert decision.triggers == []
    assert decision.re_analysis_recommended is False
    assert decision.revision_trigger_reason is None
    assert decision.engine_rule_version == FRESHNESS_ENGINE_VERSION


def test_trigger_on_revalidation_material_change(session):
    prediction = _make_prediction(session, with_fresh_market_data=False)

    decision = evaluate_prediction_freshness(session, prediction, evaluated_at=AS_OF)

    assert decision.revalidation_outcome != OUTCOME_UNCHANGED
    triggers = [t["trigger"] for t in decision.triggers]
    assert TRIGGER_REVALIDATION_MATERIAL_CHANGE in triggers
    assert decision.re_analysis_recommended is True
    assert decision.revision_trigger_reason == REASON_MATERIAL_EVIDENCE_CHANGE


def test_trigger_on_feature_drift(session):
    prediction = _make_prediction(session)
    session.add(FeatureDriftAssessment(
        model_version=MODEL_VERSION, feature_name=FEATURE_SMA20_DISTANCE, monitoring_window_label="w",
        monitoring_sample_count=25, monitoring_mean=Decimal("0.5"), drift_magnitude=Decimal("3"),
        verdict="DRIFT_DETECTED", trust_reduction_recommended=True, evaluated_at=AS_OF, drift_rule_version="FDM-001",
    ))
    session.commit()

    decision = evaluate_prediction_freshness(session, prediction, evaluated_at=AS_OF)

    triggers = [t["trigger"] for t in decision.triggers]
    assert TRIGGER_FEATURE_DRIFT_DETECTED in triggers
    assert decision.re_analysis_recommended is True


def test_trigger_on_coverage_drift(session):
    from app.models import CoverageDriftAssessment
    prediction = _make_prediction(session)
    session.add(CoverageDriftAssessment(
        model_version=MODEL_VERSION, reference_window_label="ref", monitoring_window_label="mon",
        reference_sample_count=25, monitoring_sample_count=25, reference_coverage_rate=Decimal("1"),
        monitoring_coverage_rate=Decimal("0.5"), coverage_rate_delta=Decimal("-0.5"), verdict="DRIFT_DETECTED",
        trust_reduction_recommended=True, evaluated_at=AS_OF, drift_rule_version="FDM-001",
    ))
    session.commit()

    decision = evaluate_prediction_freshness(session, prediction, evaluated_at=AS_OF)

    triggers = [t["trigger"] for t in decision.triggers]
    assert TRIGGER_COVERAGE_DRIFT_DETECTED in triggers


def test_trigger_on_fundamental_provider_disagreement(session):
    prediction = _make_prediction(session)
    session.add(FundamentalConsensusAssessment(
        stock_id=prediction.stock_id, period_end_date=date(2026, 12, 31), metric_name="EPS", source_count=2,
        sources_considered=["yahoo-finance", "alpha-vantage"], weighted_mean=Decimal("3.5"),
        max_relative_deviation=Decimal("0.5"), verdict="MATERIAL_DISAGREEMENT", trust_reduction_recommended=True,
        evaluated_at=AS_OF, consensus_rule_version="PEC-001",
    ))
    session.commit()

    decision = evaluate_prediction_freshness(session, prediction, evaluated_at=AS_OF)

    triggers = [t["trigger"] for t in decision.triggers]
    assert TRIGGER_FUNDAMENTAL_PROVIDER_DISAGREEMENT in triggers


def test_idempotent(session):
    prediction = _make_prediction(session)

    first = evaluate_prediction_freshness(session, prediction, evaluated_at=AS_OF)
    second = evaluate_prediction_freshness(session, prediction, evaluated_at=AS_OF)

    assert first.id == second.id
    assert len(get_freshness_history(session, prediction.id)) == 1
