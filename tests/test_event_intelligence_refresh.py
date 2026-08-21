from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.event_intelligence_refresh import (
    get_event_driven_refresh_history,
    get_pending_event_backlog,
    run_event_driven_refresh,
)
from app.models import MarketPrice, NewsEventRecord, Prediction, Stock
from app.schedule_orchestration import (
    OPERATION_EVENT_TRIGGER_PROCESSING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    TRIGGER_EVENT_DRIVEN,
    ConcurrentExecutionError,
    acquire_execution,
)

import app.event_intelligence_refresh as event_intelligence_refresh

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


def _make_stock_with_open_prediction(session, symbol="AAA"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
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


def _add_high_materiality_news(session, stock, external_id="ext-1"):
    session.add(NewsEventRecord(
        stock_id=stock.id, source="finnhub", external_id=external_id, headline="Big news", event_type="EARNINGS",
        materiality="HIGH", published_at=AS_OF, fetched_at=AS_OF, ingestion_rule_version="NEI-001",
    ))
    session.commit()


def test_run_processes_new_triggers_and_records_completion(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    _add_high_materiality_news(session, stock)

    outcome = run_event_driven_refresh(session, stock.id, as_of=AS_OF, trigger_source="tick-1")

    assert outcome.is_duplicate is False
    assert len(outcome.new_triggers) == 1
    assert outcome.execution.status == STATUS_COMPLETED
    assert outcome.execution.operation_name == OPERATION_EVENT_TRIGGER_PROCESSING


def test_low_materiality_event_completes_with_no_new_triggers(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    session.add(NewsEventRecord(
        stock_id=stock.id, source="finnhub", external_id="ext-low", headline="Minor update", event_type="OTHER",
        materiality="LOW", published_at=AS_OF, fetched_at=AS_OF, ingestion_rule_version="NEI-001",
    ))
    session.commit()

    outcome = run_event_driven_refresh(session, stock.id, as_of=AS_OF, trigger_source="tick-1")

    assert outcome.is_duplicate is False
    assert outcome.new_triggers == ()
    assert outcome.execution.status == STATUS_COMPLETED


def test_duplicate_trigger_source_is_a_no_op(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    _add_high_materiality_news(session, stock)

    first = run_event_driven_refresh(session, stock.id, as_of=AS_OF, trigger_source="tick-1")
    _add_high_materiality_news(session, stock, external_id="ext-2")  # a second event exists now
    second = run_event_driven_refresh(session, stock.id, as_of=AS_OF, trigger_source="tick-1")

    assert first.is_duplicate is False
    assert second.is_duplicate is True
    assert second.new_triggers == ()  # never re-ran, even though a new event exists
    assert second.execution.id == first.execution.id


def test_a_new_trigger_source_reprocesses_and_picks_up_new_events(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    _add_high_materiality_news(session, stock, external_id="ext-1")

    run_event_driven_refresh(session, stock.id, as_of=AS_OF, trigger_source="tick-1")
    _add_high_materiality_news(session, stock, external_id="ext-2")
    second = run_event_driven_refresh(session, stock.id, as_of=AS_OF, trigger_source="tick-2")

    assert second.is_duplicate is False
    assert len(second.new_triggers) == 1  # only the newly-added event, M1.106's own dedup skips ext-1


def test_concurrent_call_for_same_stock_is_rejected(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    acquire_execution(
        session,
        operation_name=OPERATION_EVENT_TRIGGER_PROCESSING,
        scope_key=str(stock.id),
        trigger_type=TRIGGER_EVENT_DRIVEN,
        trigger_source="other-in-flight-trigger",
        triggered_at=AS_OF,
    )

    with pytest.raises(ConcurrentExecutionError):
        run_event_driven_refresh(session, stock.id, as_of=AS_OF, trigger_source="tick-1")


def test_failure_is_recorded_and_reraised(session, monkeypatch):
    stock, prediction = _make_stock_with_open_prediction(session)
    _add_high_materiality_news(session, stock)

    def _boom(*args, **kwargs):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr(event_intelligence_refresh, "process_event_triggers_for_stock", _boom)

    with pytest.raises(RuntimeError, match="provider timeout"):
        run_event_driven_refresh(session, stock.id, as_of=AS_OF, trigger_source="tick-1")

    history = get_event_driven_refresh_history(session, stock.id)
    assert len(history) == 1
    assert history[0].status == STATUS_FAILED
    assert history[0].failure_reason == "provider timeout"


def test_failed_run_releases_the_lock_for_a_retry(session, monkeypatch):
    stock, prediction = _make_stock_with_open_prediction(session)
    _add_high_materiality_news(session, stock)

    monkeypatch.setattr(
        event_intelligence_refresh,
        "process_event_triggers_for_stock",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(RuntimeError):
        run_event_driven_refresh(session, stock.id, as_of=AS_OF, trigger_source="tick-1")

    monkeypatch.undo()
    retry = run_event_driven_refresh(session, stock.id, as_of=AS_OF, trigger_source="tick-2")
    assert retry.is_duplicate is False
    assert retry.execution.status == STATUS_COMPLETED


def test_pending_event_backlog_is_empty_for_a_stock_with_no_unprocessed_triggers(session):
    stock, prediction = _make_stock_with_open_prediction(session)
    _add_high_materiality_news(session, stock)
    run_event_driven_refresh(session, stock.id, as_of=AS_OF, trigger_source="tick-1")

    assert get_pending_event_backlog(session, stock.id) == ()


def test_pending_event_backlog_surfaces_unprocessed_trigger_rows(session):
    from app.models import EventTriggerRecord

    stock, prediction = _make_stock_with_open_prediction(session)
    session.add(EventTriggerRecord(
        stock_id=stock.id, event_type="MAJOR_NEWS", source_table="news_event_records", source_id="orphan-1",
        detected_at=AS_OF, materiality_note=None, affected_prediction_count=0, triggered_decision_ids=[],
        processed_at=None, trigger_rule_version="EDR-001",
    ))
    session.commit()

    backlog = get_pending_event_backlog(session, stock.id)
    assert len(backlog) == 1
    assert backlog[0].source_id == "orphan-1"

    assert get_pending_event_backlog(session) == backlog  # unfiltered call finds it too
