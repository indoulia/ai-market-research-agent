"""EPIC-M1.118: one authoritative orchestration layer that decides *when*
MRA discovery, refresh, analysis, prediction, monitoring, outcome
evaluation and learning operations execute -- so no individual capability
ever needs (or is allowed) to invent its own hidden scheduler.

This module does not itself call any domain operation (discovery, refresh,
event processing, snapshotting, learning) -- those already exist as plain,
directly-callable functions (`app.continuous_discovery`,
`app.event_driven_refresh`, `app.daily_prediction_snapshot`, ...), each of
which already routes through the provider abstraction (M1.90/M1.92/M1.94)
on its own. This module's only job is the four things every one of those
callers would otherwise have to reinvent for itself: (1) an explicit,
versioned trigger policy per operation so no cron/job is undocumented,
(2) a market-session/calendar gate, (3) a DB-enforced concurrency lock so
the same operation+scope can never run twice at once, and (4) an
append-only attempt/retry history that makes duplicate triggers a no-op
rather than a duplicate side effect.

**Idempotent duplicate triggers** (scope: "duplicate triggers do not
duplicate predictions, evidence or outcomes"): every trigger is identified
by a `dedup_key` of `(operation_name, scope_key, trigger_type,
trigger_source)`. If a `COMPLETED` attempt already exists for that exact
key, `acquire_execution` hands back that existing record instead of
letting the caller re-run the operation -- the same "return the existing
attempt rather than record a redundant one" pattern M1.35's
`record_fetch_attempt` already established.

**Conflicting concurrent executions** (scope: "prevent conflicting
concurrent executions"): guarded by a real DB unique constraint on
`(operation_name, scope_key)` in `orchestration_execution_locks`, not an
in-process check -- inserting a second lock row for the same operation+
scope raises `IntegrityError`, which this module turns into
`ConcurrentExecutionError` for the caller. The lock is released (row
deleted) when the attempt completes or fails, so it never blocks a later,
legitimate run.

**Safe retries** (scope: "failed work can be retried safely"): a failed
attempt is recorded, never overwritten, and `attempt_number` increments
per retry of the same `dedup_key`; `should_retry` refuses once
`DEFAULT_MAX_RETRIES` consecutive failures have accumulated for that key,
so a permanently-broken trigger cannot retry forever.

**Missed schedules** (scope: "detect missed schedules and support
recovery"): `detect_missed_schedule` is a pure function of the policy's
cadence and the last successful execution's timestamp -- it does not
require a "the orchestrator was continuously running" assumption, so it
works correctly even after downtime.

**Market sessions and calendar** (scope: "market-calendar aware",
"respect market holidays and sessions"): `classify_session` provides the
real, working part of this -- NSE's Monday-Friday, 09:15-15:30 IST
trading window, using `zoneinfo` rather than a hardcoded offset so it is
correct regardless of the platform's own local timezone. Holiday
exclusion is a real mechanism (`holiday_dates`) but this module carries
no canonical NSE holiday calendar of its own -- M1.118 depends only on
M1.35/M1.78/M1.90/M1.92/M1.94, not on M1.121 ("Market Calendar & Operational
Window Management"), which is the future EPIC responsible for supplying
that authoritative list. Callers who already have one today can pass it
in; until M1.121 lands, an empty `holiday_dates` set means only the
weekday/time gate applies -- an honest gap, not a fabricated one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import OrchestrationExecution, OrchestrationExecutionLock

ORCHESTRATION_RULE_VERSION = "ESO-001"

# --- Trigger types (EPIC scope: "Core Trigger Types") -----------------
TRIGGER_SCHEDULED = "SCHEDULED"
TRIGGER_EVENT_DRIVEN = "EVENT_DRIVEN"
TRIGGER_PREDICTION_DRIVEN = "PREDICTION_DRIVEN"
TRIGGER_END_OF_DAY = "END_OF_DAY"

TRIGGER_TYPES = (TRIGGER_SCHEDULED, TRIGGER_EVENT_DRIVEN, TRIGGER_PREDICTION_DRIVEN, TRIGGER_END_OF_DAY)

# --- Known recurring MRA operations ------------------------------------
# Every name here composes an already-existing, directly-callable domain
# function; this module never defines a new one.
OPERATION_DAILY_DISCOVERY = "DAILY_DISCOVERY"                    # app.continuous_discovery
OPERATION_PRICE_MONITORING = "PRICE_MONITORING"                  # app.market_data ingest + app.scan
OPERATION_NEWS_EVENT_REFRESH = "NEWS_EVENT_REFRESH"               # app.news_data.ingest
OPERATION_FUNDAMENTALS_REFRESH = "FUNDAMENTALS_REFRESH"           # app.fundamental_data.ingest
OPERATION_EVENT_TRIGGER_PROCESSING = "EVENT_TRIGGER_PROCESSING"   # app.event_driven_refresh
OPERATION_PREDICTION_MONITORING = "PREDICTION_MONITORING"         # app.prediction_freshness_engine / evidence_revalidation
OPERATION_END_OF_DAY_SNAPSHOT = "END_OF_DAY_SNAPSHOT"             # app.daily_prediction_snapshot / outcome_measurement
OPERATION_LEARNING_CYCLE = "LEARNING_CYCLE"                       # app.continuous_self_learning_loop

STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"

DEFAULT_MAX_RETRIES = 3

# NSE regular trading session, IST. A future EPIC (M1.121) owns the
# authoritative market-calendar/holiday data; this module only owns the
# weekday/time gate plus an injectable holiday set (see module docstring).
MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")
PRE_MARKET_START = time(9, 0)
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
POST_MARKET_END = time(17, 0)

SESSION_PRE_MARKET = "PRE_MARKET"
SESSION_MARKET_HOURS = "MARKET_HOURS"
SESSION_POST_MARKET = "POST_MARKET"
SESSION_CLOSED = "CLOSED"


class ConcurrentExecutionError(RuntimeError):
    """Raised when a second execution is attempted for an
    (operation_name, scope_key) pair that already has one in flight."""


class UnknownOperationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TriggerPolicy:
    operation_name: str
    trigger_type: str
    cadence: timedelta | None  # None for pure event/prediction-driven operations
    requires_market_session: bool
    description: str


# Fixed, documented, versioned trigger policy per operation (scope: "every
# recurring MRA operation has an explicit trigger policy"; "no operation
# relies on an undocumented cron/job").
TRIGGER_POLICIES: dict[str, TriggerPolicy] = {
    OPERATION_DAILY_DISCOVERY: TriggerPolicy(
        operation_name=OPERATION_DAILY_DISCOVERY,
        trigger_type=TRIGGER_SCHEDULED,
        cadence=timedelta(days=1),
        requires_market_session=False,
        description="Runs once per calendar day, pre-market, so newly discovered candidates are qualified before the session opens.",
    ),
    OPERATION_PRICE_MONITORING: TriggerPolicy(
        operation_name=OPERATION_PRICE_MONITORING,
        trigger_type=TRIGGER_SCHEDULED,
        cadence=timedelta(minutes=15),
        requires_market_session=True,
        description="Polls price/volume data only while the market is open; outside session hours there is nothing new to observe.",
    ),
    OPERATION_NEWS_EVENT_REFRESH: TriggerPolicy(
        operation_name=OPERATION_NEWS_EVENT_REFRESH,
        trigger_type=TRIGGER_SCHEDULED,
        cadence=timedelta(hours=1),
        requires_market_session=False,
        description="News/events happen around the clock, so this runs on a fixed cadence regardless of market session.",
    ),
    OPERATION_FUNDAMENTALS_REFRESH: TriggerPolicy(
        operation_name=OPERATION_FUNDAMENTALS_REFRESH,
        trigger_type=TRIGGER_SCHEDULED,
        cadence=timedelta(days=1),
        requires_market_session=False,
        description="Fundamental data changes slowly (M1.35's own 90-day freshness policy); once a day is sufficient.",
    ),
    OPERATION_EVENT_TRIGGER_PROCESSING: TriggerPolicy(
        operation_name=OPERATION_EVENT_TRIGGER_PROCESSING,
        trigger_type=TRIGGER_EVENT_DRIVEN,
        cadence=None,
        requires_market_session=False,
        description="Fires whenever M1.106's event detection surfaces a new major-news/corporate-action/shock/regime trigger.",
    ),
    OPERATION_PREDICTION_MONITORING: TriggerPolicy(
        operation_name=OPERATION_PREDICTION_MONITORING,
        trigger_type=TRIGGER_PREDICTION_DRIVEN,
        cadence=None,
        requires_market_session=True,
        description="Fires when an open prediction's target, stop-loss, horizon or underlying assumption may have changed; only meaningful while prices can move.",
    ),
    OPERATION_END_OF_DAY_SNAPSHOT: TriggerPolicy(
        operation_name=OPERATION_END_OF_DAY_SNAPSHOT,
        trigger_type=TRIGGER_END_OF_DAY,
        cadence=timedelta(days=1),
        requires_market_session=False,
        description="Runs once after market close to snapshot canonical daily state and close outcomes for the day.",
    ),
    OPERATION_LEARNING_CYCLE: TriggerPolicy(
        operation_name=OPERATION_LEARNING_CYCLE,
        trigger_type=TRIGGER_END_OF_DAY,
        cadence=timedelta(days=1),
        requires_market_session=False,
        description="Runs once after the end-of-day snapshot so the learning loop always sees a complete day's evidence.",
    ),
}


def get_trigger_policy(operation_name: str) -> TriggerPolicy:
    policy = TRIGGER_POLICIES.get(operation_name)
    if policy is None:
        raise UnknownOperationError(f"no trigger policy defined for operation: {operation_name}")
    return policy


def classify_session(at: datetime, *, holiday_dates: frozenset[date] = frozenset()) -> str:
    """Classifies `at` (any aware or naive-UTC-by-convention datetime,
    per this codebase's timestamp convention) into the trading-day window
    it falls in, in NSE local time. Weekends and `holiday_dates` are
    always `SESSION_CLOSED`, regardless of time of day."""
    local = at.astimezone(MARKET_TIMEZONE) if at.tzinfo is not None else at.replace(tzinfo=ZoneInfo("UTC")).astimezone(MARKET_TIMEZONE)
    if local.weekday() >= 5 or local.date() in holiday_dates:
        return SESSION_CLOSED

    local_time = local.time()
    if PRE_MARKET_START <= local_time < MARKET_OPEN:
        return SESSION_PRE_MARKET
    if MARKET_OPEN <= local_time < MARKET_CLOSE:
        return SESSION_MARKET_HOURS
    if MARKET_CLOSE <= local_time < POST_MARKET_END:
        return SESSION_POST_MARKET
    return SESSION_CLOSED


def is_trading_session(at: datetime, *, holiday_dates: frozenset[date] = frozenset()) -> bool:
    return classify_session(at, holiday_dates=holiday_dates) == SESSION_MARKET_HOURS


def _build_dedup_key(*, operation_name: str, scope_key: str, trigger_type: str, trigger_source: str | None) -> str:
    return f"{operation_name}:{scope_key}:{trigger_type}:{trigger_source or ''}"


@dataclass(frozen=True)
class ExecutionClaim:
    """The result of `acquire_execution`. When `is_duplicate` is True, the
    caller must not run the operation again -- `existing` is the
    already-`COMPLETED` record from the earlier, identical trigger."""

    operation_name: str
    scope_key: str
    trigger_type: str
    trigger_source: str | None
    dedup_key: str
    triggered_at: datetime
    attempt_number: int
    is_duplicate: bool
    existing: OrchestrationExecution | None


def acquire_execution(
    session: Session,
    *,
    operation_name: str,
    scope_key: str,
    trigger_type: str,
    trigger_source: str | None,
    triggered_at: datetime,
) -> ExecutionClaim:
    """Claims the right to run `operation_name` for `scope_key` right now.

    Returns a duplicate claim (no lock held) if this exact trigger has
    already completed successfully. Otherwise attempts to take the
    concurrency lock; raises `ConcurrentExecutionError` if another
    attempt for the same `(operation_name, scope_key)` is already in
    flight, regardless of whether it is the same trigger."""
    get_trigger_policy(operation_name)  # raises UnknownOperationError early if misconfigured
    dedup_key = _build_dedup_key(
        operation_name=operation_name, scope_key=scope_key, trigger_type=trigger_type, trigger_source=trigger_source
    )

    existing_completed = session.scalar(
        select(OrchestrationExecution)
        .where(OrchestrationExecution.dedup_key == dedup_key, OrchestrationExecution.status == STATUS_COMPLETED)
        .order_by(OrchestrationExecution.id.desc())
    )
    if existing_completed is not None:
        return ExecutionClaim(
            operation_name=operation_name,
            scope_key=scope_key,
            trigger_type=trigger_type,
            trigger_source=trigger_source,
            dedup_key=dedup_key,
            triggered_at=triggered_at,
            attempt_number=existing_completed.attempt_number,
            is_duplicate=True,
            existing=existing_completed,
        )

    prior_attempts = session.scalar(
        select(OrchestrationExecution)
        .where(OrchestrationExecution.dedup_key == dedup_key)
        .order_by(OrchestrationExecution.attempt_number.desc())
    )
    attempt_number = (prior_attempts.attempt_number + 1) if prior_attempts is not None else 1

    lock = OrchestrationExecutionLock(
        operation_name=operation_name,
        scope_key=scope_key,
        trigger_type=trigger_type,
        acquired_at=triggered_at,
        orchestration_rule_version=ORCHESTRATION_RULE_VERSION,
    )
    session.add(lock)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConcurrentExecutionError(
            f"an execution for operation={operation_name!r} scope_key={scope_key!r} is already in flight"
        ) from exc

    return ExecutionClaim(
        operation_name=operation_name,
        scope_key=scope_key,
        trigger_type=trigger_type,
        trigger_source=trigger_source,
        dedup_key=dedup_key,
        triggered_at=triggered_at,
        attempt_number=attempt_number,
        is_duplicate=False,
        existing=None,
    )


def _release_lock(session: Session, claim: ExecutionClaim) -> None:
    lock = session.scalar(
        select(OrchestrationExecutionLock).where(
            OrchestrationExecutionLock.operation_name == claim.operation_name,
            OrchestrationExecutionLock.scope_key == claim.scope_key,
        )
    )
    if lock is not None:
        session.delete(lock)


def complete_execution(
    session: Session, claim: ExecutionClaim, *, started_at: datetime, completed_at: datetime
) -> OrchestrationExecution:
    """Records a successful attempt and releases the concurrency lock.
    Must not be called on a duplicate claim (nothing was run)."""
    if claim.is_duplicate:
        raise ValueError("cannot complete a duplicate claim -- the operation was never run")

    execution = OrchestrationExecution(
        operation_name=claim.operation_name,
        trigger_type=claim.trigger_type,
        trigger_source=claim.trigger_source,
        scope_key=claim.scope_key,
        dedup_key=claim.dedup_key,
        attempt_number=claim.attempt_number,
        status=STATUS_COMPLETED,
        triggered_at=claim.triggered_at,
        started_at=started_at,
        completed_at=completed_at,
        failure_reason=None,
        orchestration_rule_version=ORCHESTRATION_RULE_VERSION,
    )
    session.add(execution)
    _release_lock(session, claim)
    session.commit()
    session.refresh(execution)
    return execution


def fail_execution(
    session: Session, claim: ExecutionClaim, *, started_at: datetime, failed_at: datetime, failure_reason: str
) -> OrchestrationExecution:
    """Records a failed attempt and releases the concurrency lock so a
    retry (subject to `should_retry`) can acquire it again."""
    if claim.is_duplicate:
        raise ValueError("cannot fail a duplicate claim -- the operation was never run")

    execution = OrchestrationExecution(
        operation_name=claim.operation_name,
        trigger_type=claim.trigger_type,
        trigger_source=claim.trigger_source,
        scope_key=claim.scope_key,
        dedup_key=claim.dedup_key,
        attempt_number=claim.attempt_number,
        status=STATUS_FAILED,
        triggered_at=claim.triggered_at,
        started_at=started_at,
        completed_at=failed_at,
        failure_reason=failure_reason,
        orchestration_rule_version=ORCHESTRATION_RULE_VERSION,
    )
    session.add(execution)
    _release_lock(session, claim)
    session.commit()
    session.refresh(execution)
    return execution


def should_retry(session: Session, dedup_key: str, *, max_retries: int = DEFAULT_MAX_RETRIES) -> bool:
    """False once a `COMPLETED` attempt exists (nothing left to retry) or
    once `max_retries` consecutive `FAILED` attempts have accumulated for
    this exact trigger (a permanently-broken trigger must not retry
    forever)."""
    rows = session.scalars(
        select(OrchestrationExecution).where(OrchestrationExecution.dedup_key == dedup_key)
    ).all()
    if any(row.status == STATUS_COMPLETED for row in rows):
        return False
    failed_count = sum(1 for row in rows if row.status == STATUS_FAILED)
    return failed_count < max_retries


def get_execution_history(
    session: Session, operation_name: str, scope_key: str | None = None
) -> tuple[OrchestrationExecution, ...]:
    stmt = select(OrchestrationExecution).where(OrchestrationExecution.operation_name == operation_name)
    if scope_key is not None:
        stmt = stmt.where(OrchestrationExecution.scope_key == scope_key)
    return tuple(session.scalars(stmt.order_by(OrchestrationExecution.id.asc())).all())


@dataclass(frozen=True)
class MissedScheduleReport:
    operation_name: str
    last_successful_at: datetime | None
    cadence: timedelta | None
    missed_cycles: int
    is_missed: bool


@dataclass(frozen=True)
class OperationalHealthSnapshot:
    """Operational health/backlog visibility for one (operation_name,
    scope_key) pair (scope: "provide operational health and backlog
    visibility") -- composed entirely from data this module already
    persists, never a separate tracked metric that could drift from the
    execution history itself."""

    operation_name: str
    scope_key: str
    trigger_type: str
    is_locked: bool
    last_execution: OrchestrationExecution | None
    missed_schedule: MissedScheduleReport
    consecutive_failure_count: int


def get_operational_health(
    session: Session, operation_name: str, scope_key: str, *, as_of: datetime
) -> OperationalHealthSnapshot:
    policy = get_trigger_policy(operation_name)

    lock = session.scalar(
        select(OrchestrationExecutionLock).where(
            OrchestrationExecutionLock.operation_name == operation_name,
            OrchestrationExecutionLock.scope_key == scope_key,
        )
    )

    history = get_execution_history(session, operation_name, scope_key)
    last_execution = history[-1] if history else None

    consecutive_failure_count = 0
    for execution in reversed(history):
        if execution.status != STATUS_FAILED:
            break
        consecutive_failure_count += 1

    missed_schedule = detect_missed_schedule(session, operation_name, scope_key, as_of=as_of)

    return OperationalHealthSnapshot(
        operation_name=operation_name,
        scope_key=scope_key,
        trigger_type=policy.trigger_type,
        is_locked=lock is not None,
        last_execution=last_execution,
        missed_schedule=missed_schedule,
        consecutive_failure_count=consecutive_failure_count,
    )


def detect_missed_schedule(
    session: Session, operation_name: str, scope_key: str, *, as_of: datetime
) -> MissedScheduleReport:
    """Purely derived from the policy's cadence and the timestamp of the
    last successful execution -- works correctly even after the
    orchestrator itself was down for a while, since it never assumes
    continuous operation (scope: "detect missed schedules and support
    recovery")."""
    policy = get_trigger_policy(operation_name)
    if policy.cadence is None:
        # Event/prediction-driven operations have no cadence to miss.
        return MissedScheduleReport(
            operation_name=operation_name, last_successful_at=None, cadence=None, missed_cycles=0, is_missed=False
        )

    last_successful_at = session.scalar(
        select(OrchestrationExecution.completed_at)
        .where(
            OrchestrationExecution.operation_name == operation_name,
            OrchestrationExecution.scope_key == scope_key,
            OrchestrationExecution.status == STATUS_COMPLETED,
        )
        .order_by(OrchestrationExecution.completed_at.desc())
    )
    if last_successful_at is None:
        # Never run yet: due immediately, but not a "missed" recurrence.
        return MissedScheduleReport(
            operation_name=operation_name, last_successful_at=None, cadence=policy.cadence, missed_cycles=0, is_missed=False
        )

    elapsed = as_of.replace(tzinfo=None) - last_successful_at.replace(tzinfo=None)
    cycles_elapsed = elapsed // policy.cadence
    missed_cycles = max(0, int(cycles_elapsed) - 1)
    return MissedScheduleReport(
        operation_name=operation_name,
        last_successful_at=last_successful_at,
        cadence=policy.cadence,
        missed_cycles=missed_cycles,
        is_missed=missed_cycles > 0,
    )
