from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.schedule_orchestration import (
    DEFAULT_MAX_RETRIES,
    OPERATION_DAILY_DISCOVERY,
    OPERATION_EVENT_TRIGGER_PROCESSING,
    OPERATION_PRICE_MONITORING,
    SESSION_CLOSED,
    SESSION_MARKET_HOURS,
    SESSION_POST_MARKET,
    SESSION_PRE_MARKET,
    TRIGGER_EVENT_DRIVEN,
    TRIGGER_POLICIES,
    TRIGGER_SCHEDULED,
    TRIGGER_TYPES,
    ConcurrentExecutionError,
    UnknownOperationError,
    acquire_execution,
    classify_session,
    complete_execution,
    detect_missed_schedule,
    fail_execution,
    get_execution_history,
    get_operational_health,
    get_trigger_policy,
    is_trading_session,
    should_retry,
)

AS_OF = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)  # a Friday


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


# --- Trigger policy completeness ---------------------------------------

def test_every_operation_has_an_explicit_trigger_policy():
    for operation_name, policy in TRIGGER_POLICIES.items():
        assert policy.operation_name == operation_name
        assert policy.trigger_type in TRIGGER_TYPES


def test_unknown_operation_raises():
    with pytest.raises(UnknownOperationError):
        get_trigger_policy("NOT_A_REAL_OPERATION")


# --- Market session / calendar awareness --------------------------------

def test_weekday_market_hours_is_market_hours():
    # 2026-08-21 is a Friday; 10:00 UTC = 15:30 IST -- just inside close.
    at = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)  # 14:30 IST
    assert classify_session(at) == SESSION_MARKET_HOURS
    assert is_trading_session(at) is True


def test_weekend_is_closed_regardless_of_time():
    saturday = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)  # Saturday
    assert classify_session(saturday) == SESSION_CLOSED
    assert is_trading_session(saturday) is False


def test_holiday_is_closed_even_on_a_weekday():
    # 2026-01-26 is a Monday.
    republic_day = datetime(2026, 1, 26, 9, 0, tzinfo=timezone.utc)
    assert classify_session(republic_day) == SESSION_MARKET_HOURS
    assert classify_session(republic_day, holiday_dates=frozenset({date(2026, 1, 26)})) == SESSION_CLOSED


def test_pre_and_post_market_windows():
    pre = datetime(2026, 8, 21, 3, 30, tzinfo=timezone.utc)  # 09:00 IST
    post = datetime(2026, 8, 21, 10, 15, tzinfo=timezone.utc)  # 15:45 IST
    assert classify_session(pre) == SESSION_PRE_MARKET
    assert classify_session(post) == SESSION_POST_MARKET


# --- Idempotent duplicate triggers ---------------------------------------

def test_duplicate_trigger_after_completion_is_a_no_op(session):
    claim = acquire_execution(
        session,
        operation_name=OPERATION_DAILY_DISCOVERY,
        scope_key="GLOBAL",
        trigger_type=TRIGGER_SCHEDULED,
        trigger_source="2026-08-21",
        triggered_at=AS_OF,
    )
    assert claim.is_duplicate is False
    complete_execution(session, claim, started_at=AS_OF, completed_at=AS_OF)

    duplicate_claim = acquire_execution(
        session,
        operation_name=OPERATION_DAILY_DISCOVERY,
        scope_key="GLOBAL",
        trigger_type=TRIGGER_SCHEDULED,
        trigger_source="2026-08-21",
        triggered_at=AS_OF + timedelta(minutes=1),
    )
    assert duplicate_claim.is_duplicate is True
    assert duplicate_claim.existing is not None
    assert duplicate_claim.existing.status == "COMPLETED"

    history = get_execution_history(session, OPERATION_DAILY_DISCOVERY, "GLOBAL")
    assert len(history) == 1  # the duplicate trigger never created a second row


# --- Concurrency lock -----------------------------------------------------

def test_concurrent_execution_for_same_operation_and_scope_is_rejected(session):
    claim = acquire_execution(
        session,
        operation_name=OPERATION_PRICE_MONITORING,
        scope_key="RELIANCE",
        trigger_type=TRIGGER_SCHEDULED,
        trigger_source="cadence",
        triggered_at=AS_OF,
    )
    assert claim.is_duplicate is False

    with pytest.raises(ConcurrentExecutionError):
        acquire_execution(
            session,
            operation_name=OPERATION_PRICE_MONITORING,
            scope_key="RELIANCE",
            trigger_type=TRIGGER_EVENT_DRIVEN,
            trigger_source="different-trigger",
            triggered_at=AS_OF,
        )


def test_lock_is_released_after_completion_allowing_a_new_run(session):
    claim = acquire_execution(
        session,
        operation_name=OPERATION_PRICE_MONITORING,
        scope_key="RELIANCE",
        trigger_type=TRIGGER_SCHEDULED,
        trigger_source="cadence-1",
        triggered_at=AS_OF,
    )
    complete_execution(session, claim, started_at=AS_OF, completed_at=AS_OF)

    next_claim = acquire_execution(
        session,
        operation_name=OPERATION_PRICE_MONITORING,
        scope_key="RELIANCE",
        trigger_type=TRIGGER_SCHEDULED,
        trigger_source="cadence-2",
        triggered_at=AS_OF + timedelta(minutes=15),
    )
    assert next_claim.is_duplicate is False


def test_lock_is_released_after_failure_allowing_a_retry(session):
    claim = acquire_execution(
        session,
        operation_name=OPERATION_EVENT_TRIGGER_PROCESSING,
        scope_key="RELIANCE",
        trigger_type=TRIGGER_EVENT_DRIVEN,
        trigger_source="trigger-1",
        triggered_at=AS_OF,
    )
    fail_execution(session, claim, started_at=AS_OF, failed_at=AS_OF, failure_reason="provider timeout")

    retry_claim = acquire_execution(
        session,
        operation_name=OPERATION_EVENT_TRIGGER_PROCESSING,
        scope_key="RELIANCE",
        trigger_type=TRIGGER_EVENT_DRIVEN,
        trigger_source="trigger-1",
        triggered_at=AS_OF + timedelta(minutes=1),
    )
    assert retry_claim.is_duplicate is False
    assert retry_claim.attempt_number == 2


# --- Retry limits -----------------------------------------------------------

def test_should_retry_false_after_max_consecutive_failures(session):
    dedup_key = None
    for attempt in range(DEFAULT_MAX_RETRIES):
        claim = acquire_execution(
            session,
            operation_name=OPERATION_EVENT_TRIGGER_PROCESSING,
            scope_key="TCS",
            trigger_type=TRIGGER_EVENT_DRIVEN,
            trigger_source="trigger-x",
            triggered_at=AS_OF,
        )
        dedup_key = claim.dedup_key
        fail_execution(session, claim, started_at=AS_OF, failed_at=AS_OF, failure_reason=f"attempt {attempt} failed")

    assert should_retry(session, dedup_key) is False


def test_should_retry_true_before_max_failures(session):
    claim = acquire_execution(
        session,
        operation_name=OPERATION_EVENT_TRIGGER_PROCESSING,
        scope_key="INFY",
        trigger_type=TRIGGER_EVENT_DRIVEN,
        trigger_source="trigger-y",
        triggered_at=AS_OF,
    )
    fail_execution(session, claim, started_at=AS_OF, failed_at=AS_OF, failure_reason="transient error")
    assert should_retry(session, claim.dedup_key) is True


def test_should_retry_false_once_completed(session):
    claim = acquire_execution(
        session,
        operation_name=OPERATION_EVENT_TRIGGER_PROCESSING,
        scope_key="HDFC",
        trigger_type=TRIGGER_EVENT_DRIVEN,
        trigger_source="trigger-z",
        triggered_at=AS_OF,
    )
    complete_execution(session, claim, started_at=AS_OF, completed_at=AS_OF)
    assert should_retry(session, claim.dedup_key) is False


# --- Missed schedule detection ----------------------------------------------

def test_missed_schedule_detected_after_downtime(session):
    claim = acquire_execution(
        session,
        operation_name=OPERATION_DAILY_DISCOVERY,
        scope_key="GLOBAL",
        trigger_type=TRIGGER_SCHEDULED,
        trigger_source="2026-08-18",
        triggered_at=AS_OF - timedelta(days=3),
    )
    complete_execution(session, claim, started_at=AS_OF - timedelta(days=3), completed_at=AS_OF - timedelta(days=3))

    report = detect_missed_schedule(session, OPERATION_DAILY_DISCOVERY, "GLOBAL", as_of=AS_OF)
    assert report.is_missed is True
    assert report.missed_cycles == 2  # 3 days elapsed on a 1-day cadence: 2 cycles missed


def test_no_missed_schedule_within_cadence_window(session):
    claim = acquire_execution(
        session,
        operation_name=OPERATION_DAILY_DISCOVERY,
        scope_key="GLOBAL",
        trigger_type=TRIGGER_SCHEDULED,
        trigger_source="2026-08-21",
        triggered_at=AS_OF,
    )
    complete_execution(session, claim, started_at=AS_OF, completed_at=AS_OF)

    report = detect_missed_schedule(session, OPERATION_DAILY_DISCOVERY, "GLOBAL", as_of=AS_OF + timedelta(hours=2))
    assert report.is_missed is False
    assert report.missed_cycles == 0


def test_missed_schedule_never_run_is_not_flagged_as_missed(session):
    report = detect_missed_schedule(session, OPERATION_DAILY_DISCOVERY, "NEVER_RUN", as_of=AS_OF)
    assert report.is_missed is False
    assert report.last_successful_at is None


def test_event_driven_operation_has_no_missed_schedule_concept(session):
    report = detect_missed_schedule(session, OPERATION_EVENT_TRIGGER_PROCESSING, "GLOBAL", as_of=AS_OF)
    assert report.is_missed is False
    assert report.cadence is None


# --- Operational health / backlog visibility --------------------------------

def test_operational_health_reflects_in_flight_lock(session):
    acquire_execution(
        session,
        operation_name=OPERATION_PRICE_MONITORING,
        scope_key="WIPRO",
        trigger_type=TRIGGER_SCHEDULED,
        trigger_source="cadence",
        triggered_at=AS_OF,
    )
    health = get_operational_health(session, OPERATION_PRICE_MONITORING, "WIPRO", as_of=AS_OF)
    assert health.is_locked is True
    assert health.last_execution is None  # nothing recorded yet -- still in flight


def test_operational_health_reports_consecutive_failure_streak(session):
    for i in range(2):
        claim = acquire_execution(
            session,
            operation_name=OPERATION_EVENT_TRIGGER_PROCESSING,
            scope_key="AXISBANK",
            trigger_type=TRIGGER_EVENT_DRIVEN,
            trigger_source=f"trigger-{i}",
            triggered_at=AS_OF,
        )
        fail_execution(session, claim, started_at=AS_OF, failed_at=AS_OF, failure_reason="boom")

    health = get_operational_health(session, OPERATION_EVENT_TRIGGER_PROCESSING, "AXISBANK", as_of=AS_OF)
    assert health.is_locked is False
    assert health.consecutive_failure_count == 2
    assert health.last_execution.status == "FAILED"


def test_operational_health_failure_streak_resets_after_success(session):
    claim = acquire_execution(
        session,
        operation_name=OPERATION_EVENT_TRIGGER_PROCESSING,
        scope_key="ITC",
        trigger_type=TRIGGER_EVENT_DRIVEN,
        trigger_source="trigger-fail",
        triggered_at=AS_OF,
    )
    fail_execution(session, claim, started_at=AS_OF, failed_at=AS_OF, failure_reason="boom")

    claim2 = acquire_execution(
        session,
        operation_name=OPERATION_EVENT_TRIGGER_PROCESSING,
        scope_key="ITC",
        trigger_type=TRIGGER_EVENT_DRIVEN,
        trigger_source="trigger-ok",
        triggered_at=AS_OF,
    )
    complete_execution(session, claim2, started_at=AS_OF, completed_at=AS_OF)

    health = get_operational_health(session, OPERATION_EVENT_TRIGGER_PROCESSING, "ITC", as_of=AS_OF)
    assert health.consecutive_failure_count == 0
