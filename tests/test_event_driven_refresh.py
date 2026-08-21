from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.event_driven_refresh import (
    EVENT_CORPORATE_ACTION,
    EVENT_MAJOR_NEWS,
    EVENT_PRICE_VOLUME_SHOCK,
    EVENT_REGIME_CHANGE,
    EVENT_TRIGGER_VERSION,
    get_trigger_history,
    process_event_triggers_for_stock,
)
from app.models import (
    CorporateAction,
    DailyCandidateScan,
    MarketPrice,
    NewsEventRecord,
    Prediction,
    RecommendationGeneration,
    RegimeTransitionAssessment,
    ScanCandidate,
    Stock,
)

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


def _make_stock_with_open_prediction(session):
    stock = Stock(symbol="AAA", exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    session.add(MarketPrice(
        stock_id=stock.id, timestamp=AS_OF, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"),
        close=Decimal("100"), volume=1000, source="test",
    ))
    prediction = Prediction(
        stock_id=stock.id, as_of_timestamp=AS_OF, entry_price=Decimal("100"), horizon_days=5,
        target_return=Decimal("0.05"), stop_return=Decimal("-0.03"), predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), model_version=MODEL_VERSION, feature_version="FV-001",
        consensus_contract_version="CC-001", horizon_selection_version="HS-001", scoring_contract_version="SC-001",
        opportunity_score=Decimal("60.00"), status="OPEN",
    )
    session.add(prediction)
    session.commit()
    return stock, prediction


def test_major_news_creates_trigger_and_revalidates_open_prediction(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    session.add(NewsEventRecord(
        stock_id=stock.id, source="finnhub", external_id="ext-1", headline="Big news", event_type="EARNINGS",
        materiality="HIGH", published_at=AS_OF, fetched_at=AS_OF, ingestion_rule_version="NEI-001",
    ))
    session.commit()

    triggers = process_event_triggers_for_stock(session, stock.id, as_of=AS_OF)

    assert len(triggers) == 1
    assert triggers[0].event_type == EVENT_MAJOR_NEWS
    assert triggers[0].affected_prediction_count == 1
    assert len(triggers[0].triggered_decision_ids) == 1
    assert triggers[0].trigger_rule_version == EVENT_TRIGGER_VERSION


def test_low_materiality_news_does_not_trigger(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    session.add(NewsEventRecord(
        stock_id=stock.id, source="finnhub", external_id="ext-2", headline="Minor update", event_type="OTHER",
        materiality="LOW", published_at=AS_OF, fetched_at=AS_OF, ingestion_rule_version="NEI-001",
    ))
    session.commit()

    triggers = process_event_triggers_for_stock(session, stock.id, as_of=AS_OF)

    assert triggers == ()


def test_dedup_same_news_does_not_retrigger(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    session.add(NewsEventRecord(
        stock_id=stock.id, source="finnhub", external_id="ext-3", headline="Big news", event_type="EARNINGS",
        materiality="HIGH", published_at=AS_OF, fetched_at=AS_OF, ingestion_rule_version="NEI-001",
    ))
    session.commit()

    first = process_event_triggers_for_stock(session, stock.id, as_of=AS_OF)
    second = process_event_triggers_for_stock(session, stock.id, as_of=AS_OF + timedelta(hours=2))

    assert len(first) == 1
    assert second == ()
    assert len(get_trigger_history(session, stock.id)) == 1


def test_corporate_action_trigger(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    session.add(CorporateAction(
        stock_id=stock.id, action_type="DIVIDEND", effective_date=date(2027, 1, 5), ratio=None,
        cash_amount=Decimal("2.00"), old_symbol=None, new_symbol=None, source="test", action_version="CPA-001",
        recorded_at=AS_OF,
    ))
    session.commit()

    triggers = process_event_triggers_for_stock(session, stock.id, as_of=AS_OF)

    assert len(triggers) == 1
    assert triggers[0].event_type == EVENT_CORPORATE_ACTION
    assert triggers[0].materiality_note == "DIVIDEND"


def test_price_volume_shock_trigger(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    scan = DailyCandidateScan(scan_date=date(2027, 1, 1), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    session.add(ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None, predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("5.0"),
        atr_percent=Decimal("0.03"), data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
        created_at=AS_OF,
    ))
    session.commit()

    triggers = process_event_triggers_for_stock(session, stock.id, as_of=AS_OF)

    assert len(triggers) == 1
    assert triggers[0].event_type == EVENT_PRICE_VOLUME_SHOCK


def test_regime_change_trigger(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    scan = DailyCandidateScan(scan_date=date(2027, 1, 1), universe_version="DCS-001", eligible_count=1, excluded_count=0)
    session.add(scan)
    session.flush()
    candidate = ScanCandidate(
        scan_id=scan.id, stock_id=stock.id, eligible=True, exclusion_reason=None, predicted_probability=Decimal("0.7"),
        confidence=Decimal("0.8"), sma20_distance=Decimal("0.03"), volume_ratio_20d=Decimal("1.0"),
        atr_percent=Decimal("0.02"), data_quality_passed=True, model_version=MODEL_VERSION, feature_version="FV-001",
    )
    session.add(candidate)
    session.flush()
    session.add(RecommendationGeneration(
        scan_candidate_id=candidate.id, outcome="QUALIFIED", consensus_contract_version="CC-001",
        failed_criteria=None, prediction_id=prediction.id,
    ))
    session.add(RegimeTransitionAssessment(
        scan_id=scan.id, previous_scan_id=None, current_regime="BULLISH_LOW_VOL", previous_regime="BEARISH_LOW_VOL",
        transition_detected=True, distance_to_boundary=Decimal("0.01"), boundary_instability_verdict="NEAR_BOUNDARY",
        uncertainty_source="MARKET", trust_reduction_recommended=True, detected_at=AS_OF,
        assessment_rule_version="RTI-001",
    ))
    session.commit()

    triggers = process_event_triggers_for_stock(session, stock.id, as_of=AS_OF)

    assert len(triggers) == 1
    assert triggers[0].event_type == EVENT_REGIME_CHANGE


def test_cooldown_prevents_duplicate_revalidation(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    session.add(NewsEventRecord(
        stock_id=stock.id, source="finnhub", external_id="ext-4", headline="News one", event_type="EARNINGS",
        materiality="HIGH", published_at=AS_OF, fetched_at=AS_OF, ingestion_rule_version="NEI-001",
    ))
    session.commit()
    first = process_event_triggers_for_stock(session, stock.id, as_of=AS_OF)
    assert first[0].affected_prediction_count == 1

    session.add(NewsEventRecord(
        stock_id=stock.id, source="finnhub", external_id="ext-5", headline="News two", event_type="EARNINGS",
        materiality="HIGH", published_at=AS_OF + timedelta(minutes=10), fetched_at=AS_OF + timedelta(minutes=10),
        ingestion_rule_version="NEI-001",
    ))
    session.commit()
    second = process_event_triggers_for_stock(session, stock.id, as_of=AS_OF + timedelta(minutes=30))

    assert len(second) == 1
    assert second[0].affected_prediction_count == 0  # still within REFRESH_COOLDOWN of the first revalidation
