"""EPIC-M1.120: react to material external-world changes without waiting
for the next scheduled refresh, by routing M1.106's own event detection
through M1.118's centralized orchestration primitives (scope/rule: "events
trigger capabilities through orchestration; event providers never call
recommendation/domain services directly").

Deliberately composes rather than reimplements the detection scope items
this EPIC lists -- "detect new material news/corporate actions/earnings/
material market or sector movements", "map events to affected securities
and active predictions", "classify materiality", "deduplicate repeated/
syndicated events", "preserve event provenance and detection timestamps"
-- all of that is already M1.106's `process_event_triggers_for_stock`
(`app/event_driven_refresh.py`): materiality thresholds, the DB-unique
`(event_type, source_table, source_id)` dedup, `EventTriggerRecord`'s own
provenance columns, and per-prediction refresh-storm cooldown. This module
never reimplements any of it.

"Handle provider disagreement and fallback" (scope) is likewise already
composed transitively: `process_event_triggers_for_stock` calls M1.105's
`evaluate_prediction_freshness`, which itself checks M1.103's fundamental
provider-consensus disagreement (`FUNDAMENTAL_PROVIDER_DISAGREEMENT`) as
one of its own triggers -- adding a second, parallel disagreement check
here would duplicate that signal, not strengthen it.

**What this module actually adds**, mapped to the scope items M1.106
alone does not cover:
- **"Trigger targeted re-fetch and re-analysis through M1.118"**:
  `run_event_driven_refresh` wraps each call to `process_event_triggers_
  for_stock` in `app.schedule_orchestration.acquire_execution`/
  `complete_execution`/`fail_execution` under `OPERATION_EVENT_TRIGGER_
  PROCESSING` -- the actual invocation point M1.118 was built for.
- **"Event-driven execution respects configured rate/cost controls"**:
  M1.118's DB-enforced concurrency lock means two overlapping calls for
  the same stock (e.g. a poll tick and a provider webhook firing close
  together) can never both run `process_event_triggers_for_stock` at
  once; the second gets `ConcurrentExecutionError` rather than racing.
- **Execution-level duplicate-call dedup** (distinct from M1.106's own
  duplicate-*event* dedup): `acquire_execution`'s `dedup_key` guards
  against the exact same invocation being repeated verbatim (a retried
  webhook delivery, a scheduler firing twice for one tick) -- callers
  must pass a `trigger_source` that is unique *per invocation* (e.g. a
  webhook delivery id, or the polling tick's own timestamp), never a
  constant, or every later legitimate call would be wrongly treated as
  a duplicate no-op. This is a second, narrower layer of dedup on top
  of M1.106's own per-event dedup, not a replacement for it.
- **Backlog/operational-health visibility**: `get_pending_event_backlog`
  surfaces `EventTriggerRecord` rows with `processed_at IS NULL` -- which
  only occurs when a prior run's execution failed *after* detecting and
  committing new triggers but *before* finishing evaluation (M1.106
  commits trigger creation and the assessment loop in separate steps).
  A failed `run_event_driven_refresh` call leaves exactly that backlog,
  and `fail_execution`'s recorded failure is what a retrier should act
  on -- this function makes that backlog visible rather than silent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .event_driven_refresh import process_event_triggers_for_stock
from .models import EventTriggerRecord, OrchestrationExecution
from .schedule_orchestration import (
    OPERATION_EVENT_TRIGGER_PROCESSING,
    TRIGGER_EVENT_DRIVEN,
    acquire_execution,
    complete_execution,
    fail_execution,
    get_execution_history,
)


@dataclass(frozen=True)
class EventDrivenRefreshOutcome:
    stock_id: int
    trigger_source: str
    is_duplicate: bool
    new_triggers: tuple[EventTriggerRecord, ...]
    execution: OrchestrationExecution


def run_event_driven_refresh(
    session: Session, stock_id: int, *, as_of: datetime, trigger_source: str
) -> EventDrivenRefreshOutcome:
    """Runs `process_event_triggers_for_stock` under M1.118's orchestration.
    `trigger_source` must be unique per invocation (see module docstring);
    an identical `(stock_id, trigger_source)` pair that already completed
    is a no-op, and an overlapping in-flight call for the same `stock_id`
    raises `ConcurrentExecutionError` (propagated, not swallowed -- the
    caller decides whether to skip or wait)."""
    claim = acquire_execution(
        session,
        operation_name=OPERATION_EVENT_TRIGGER_PROCESSING,
        scope_key=str(stock_id),
        trigger_type=TRIGGER_EVENT_DRIVEN,
        trigger_source=trigger_source,
        triggered_at=as_of,
    )
    if claim.is_duplicate:
        return EventDrivenRefreshOutcome(
            stock_id=stock_id,
            trigger_source=trigger_source,
            is_duplicate=True,
            new_triggers=(),
            execution=claim.existing,
        )

    try:
        new_triggers = process_event_triggers_for_stock(session, stock_id, as_of=as_of)
    except Exception as exc:
        fail_execution(session, claim, started_at=as_of, failed_at=as_of, failure_reason=str(exc))
        raise

    execution = complete_execution(session, claim, started_at=as_of, completed_at=as_of)
    return EventDrivenRefreshOutcome(
        stock_id=stock_id,
        trigger_source=trigger_source,
        is_duplicate=False,
        new_triggers=new_triggers,
        execution=execution,
    )


def get_pending_event_backlog(
    session: Session, stock_id: int | None = None
) -> tuple[EventTriggerRecord, ...]:
    """Events detected but not yet fully processed -- see module
    docstring for why this can be non-empty (a failed run between
    trigger creation and completion)."""
    stmt = select(EventTriggerRecord).where(EventTriggerRecord.processed_at.is_(None))
    if stock_id is not None:
        stmt = stmt.where(EventTriggerRecord.stock_id == stock_id)
    return tuple(session.scalars(stmt.order_by(EventTriggerRecord.detected_at.asc())).all())


def get_event_driven_refresh_history(session: Session, stock_id: int) -> tuple[OrchestrationExecution, ...]:
    return get_execution_history(session, OPERATION_EVENT_TRIGGER_PROCESSING, str(stock_id))
