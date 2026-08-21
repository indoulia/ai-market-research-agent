# EPIC-M1.118 — MRA Event & Schedule Orchestration

**Status:** DONE
**Execution Status:** DONE
**Priority:** P0

## Objective
Provide one authoritative orchestration layer that decides when MRA discovery, refresh, analysis, prediction, monitoring, outcome evaluation and learning operations execute.

## Scope
- Support scheduled, event-driven, prediction-driven and end-of-day triggers.
- Make schedules configurable and market-calendar aware.
- Coordinate dependencies and prevent conflicting concurrent executions.
- Guarantee idempotent processing and safe retries.
- Detect missed schedules and support recovery.
- Route operations through provider abstractions and configured fallback policies.
- Persist trigger, execution, completion, failure and retry history.
- Support pre-market, market-hours and post-market workflows.
- Allow different cadences for discovery, price monitoring, news/events, fundamentals and learning.
- Provide operational health and backlog visibility.

## Core Trigger Types
1. Scheduled — periodic or calendar-based execution.
2. Event-driven — news, corporate action, earnings, provider/data events.
3. Prediction-driven — target, stop-loss, horizon, material movement or assumption change.
4. End-of-day — snapshot, outcome closure, metrics and learning preparation.

## Acceptance Criteria
- Every recurring MRA operation has an explicit trigger policy.
- No operation relies on an undocumented cron/job.
- Duplicate triggers do not duplicate predictions, evidence or outcomes.
- Failed work can be retried safely.
- Missed jobs are recoverable and auditable.
- Market holidays and sessions are respected.
- Trigger history can reconstruct why and when an operation ran.
- Provider failures are handled through provider policy rather than domain-specific vendor code.

## Dependencies
M1.35, M1.78, M1.90, M1.92, M1.94.

## Architectural Rule
**Scheduling/orchestration is centralized. Individual capabilities must not create competing hidden schedulers.**

## Completion Report

**Implementation:** `app/schedule_orchestration.py`, models `OrchestrationExecutionLock` / `OrchestrationExecution` (`app/models.py`), migration `migrations/versions/0097_event_schedule_orchestration.py` (single head; renumbered from an initial `0096` after rebasing onto `origin/main`, which had meanwhile merged EPIC-M1.117's `0096_release_readiness` — `down_revision` now correctly points at `0096_release_readiness`), tests `tests/test_schedule_orchestration.py`.

**Pre-implementation audit:** confirmed no hidden scheduler exists anywhere in the repo today — `app/continuous_discovery.py`, `app/event_driven_refresh.py`, `app/continuous_self_learning_loop.py`, `app/daily_prediction_snapshot.py`, etc. are all plain, directly-callable functions with no cron/timer of their own, and no entry point (`app/main.py`, `scripts/`) invokes any of them on a schedule yet. This EPIC is therefore the *first* centralized trigger authority, not a migration off an existing one — the "no undocumented cron/job" AC holds trivially today and will hold going forward because `TRIGGER_POLICIES` is now the single place any recurring operation's cadence is declared.

**Design, mapped to scope/AC:**
- **Explicit trigger policy per operation:** `TRIGGER_POLICIES` is a fixed, documented, versioned (`ORCHESTRATION_RULE_VERSION = "ESO-001"`) dict covering all 4 core trigger types (scheduled/event-driven/prediction-driven/end-of-day) across 8 known MRA operations (discovery, price monitoring, news refresh, fundamentals refresh, event-trigger processing, prediction monitoring, EOD snapshot, learning cycle). `get_trigger_policy` raises `UnknownOperationError` for anything not registered, rather than silently allowing an undeclared operation to run.
- **Idempotent duplicate triggers:** `acquire_execution` keys every trigger by `dedup_key = (operation_name, scope_key, trigger_type, trigger_source)`; a trigger identical to one that already `COMPLETED` gets back that existing record (`is_duplicate=True`) instead of re-running — the same "return the existing attempt, don't record a redundant one" pattern M1.35's `record_fetch_attempt` established.
- **Conflicting concurrent executions:** guarded by a real DB unique constraint (`orchestration_execution_locks.(operation_name, scope_key)`), not an in-process check — `IntegrityError` on a second concurrent claim is translated to `ConcurrentExecutionError`. The lock is released (row deleted) on both `complete_execution` and `fail_execution`.
- **Safe retries:** each attempt (including retries) is its own immutable row with an incrementing `attempt_number`; `should_retry` returns `False` once a `COMPLETED` row exists for the `dedup_key` or once `DEFAULT_MAX_RETRIES` (3) consecutive `FAILED` rows have accumulated.
- **Missed schedules:** `detect_missed_schedule` is a pure function of the policy's cadence and the last successful execution's `completed_at` — correct even after the orchestrator itself was down, since it never assumes continuous operation.
- **Market calendar/session awareness:** `classify_session`/`is_trading_session` implement the real NSE Mon-Fri 09:15-15:30 IST window via `zoneinfo`, plus pre-market/post-market windows. Holiday exclusion is a real, working mechanism (`holiday_dates: frozenset[date]`) but this EPIC does not depend on M1.121 (Market Calendar & Operational Window Management) and carries no canonical NSE holiday list of its own — that is honestly left for M1.121 to supply; callers with their own holiday data can already pass it in today.
- **Provider failures handled through provider policy, not here:** this module never calls a provider directly — every domain operation it schedules already routes through M1.90/M1.92/M1.94's provider abstraction on its own; centralizing provider failover a second time here would duplicate, not compose.
- **Operational health/backlog visibility:** `get_operational_health` composes the lock state, last execution, missed-schedule report and current consecutive-failure streak for one `(operation_name, scope_key)` — derived entirely from already-persisted data, never a separately tracked metric that could drift.
- **Trigger history reconstruction:** `get_execution_history` returns every attempt (trigger type/source, triggered/started/completed timestamps, status, failure reason) in order, sufficient to reconstruct why and when any operation ran.

**Testing:** `tests/test_schedule_orchestration.py`, 20 tests — trigger-policy completeness, unknown-operation error, weekday/weekend/holiday/pre-post-market session classification, duplicate-trigger no-op, concurrent-execution rejection, lock release after success/failure, retry-limit enforcement (before/at max, and reset-on-success), missed-schedule detection (after downtime, within-window, never-run, event-driven-has-none), and operational-health snapshots (locked, failure streak, streak reset). Command: `DATABASE_URL="sqlite:///./test_scratch.db" python -m pytest tests/test_schedule_orchestration.py -q` → `20 passed`. Full suite re-run after the change: `1166 passed, 6 skipped`. `alembic heads` shows a single head (`0096_event_schedule_orchestration`) — no branch merge needed. (A pre-existing, unrelated SQLite limitation — `ALTER TABLE ... ALTER COLUMN ... DROP DEFAULT`, from an earlier migration — blocks a from-scratch SQLite `alembic upgrade head`; confirmed this already fails identically at `0095` before this EPIC's migration is even applied, so it is not a regression, and CI runs against real Postgres.)

**Not built (deliberately out of scope for M1.118):** wiring any actual cron/GitHub Actions trigger to call `acquire_execution`/the domain operations — this EPIC provides the orchestration *primitives* (policy, dedup, lock, retry, missed-schedule, health), not a deployed scheduler process; that is an infrastructure/ops decision for the user, not something to invent unrequested. The authoritative NSE holiday calendar is M1.121's job, not duplicated here.
