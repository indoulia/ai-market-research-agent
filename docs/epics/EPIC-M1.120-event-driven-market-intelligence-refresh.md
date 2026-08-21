# EPIC-M1.120 — Event-Driven Market Intelligence Refresh

**Status:** APPROVED
**Execution Status:** VALIDATING
**Priority:** P0

## Objective
Ensure MRA reacts to material external-world changes instead of waiting for the next scheduled refresh.

## Scope
- Detect new material news through provider contracts.
- Detect corporate actions and earnings/events through provider contracts.
- Detect material market/sector movements.
- Map events to affected securities and active predictions.
- Classify materiality, freshness and affected horizon.
- Trigger targeted re-fetch and re-analysis through M1.118.
- Deduplicate repeated/syndicated events.
- Preserve event provenance and detection timestamps.
- Avoid unnecessary re-analysis for immaterial events.
- Handle provider disagreement and fallback.

## Event Classes
- News
- Corporate action
- Earnings/results
- Material company event
- Material market movement
- Material sector/industry movement
- Provider/data correction

## Acceptance Criteria
- Material events can trigger analysis without waiting for the next scheduled cycle.
- Event-to-security mapping is deterministic and auditable.
- Duplicate events do not create duplicate revisions.
- Event-triggered predictions preserve prior versions.
- Event freshness and provider provenance are recorded.
- Event-driven execution respects configured rate/cost controls.

## Dependencies
M1.73, M1.90, M1.94, M1.106, M1.118.

## Architectural Rule
**Events trigger capabilities through orchestration; event providers never call recommendation/domain services directly.**

## Completion Report

**Implementation:** `app/event_intelligence_refresh.py`, tests `tests/test_event_intelligence_refresh.py`. No migration/model changes -- this EPIC adds no new persisted state.

**Design:** composes M1.106's `process_event_triggers_for_stock` (`app/event_driven_refresh.py`) for all detection/materiality/mapping/dedup/provenance scope items, and M1.118's `app/schedule_orchestration.py` for the one thing M1.106 didn't yet have: an actual orchestrated invocation point.
- `run_event_driven_refresh(session, stock_id, *, as_of, trigger_source)` wraps one call to `process_event_triggers_for_stock` in `acquire_execution`/`complete_execution`/`fail_execution` under `OPERATION_EVENT_TRIGGER_PROCESSING` — satisfying "trigger targeted re-fetch and re-analysis through M1.118" literally, not just by convention.
- **Concurrency / rate control:** M1.118's DB-enforced lock means two overlapping calls for the same stock can't both run at once; the second raises `ConcurrentExecutionError`, propagated to the caller.
- **Two dedup layers, deliberately distinct:** M1.106's own `(event_type, source_table, source_id)` constraint dedupes *events*; this module's `dedup_key` (via `trigger_source`, which callers must make unique per invocation) dedupes *invocations* — guards against a retried webhook or a scheduler double-fire re-running the same call, without ever treating "a new event arrived" as a duplicate (verified by `test_a_new_trigger_source_reprocesses_and_picks_up_new_events`).
- **Provider disagreement/fallback:** composed transitively — `process_event_triggers_for_stock` → M1.105's `evaluate_prediction_freshness` → M1.103's fundamental-provider-disagreement check. Not reimplemented here.
- **Backlog visibility:** `get_pending_event_backlog` surfaces `EventTriggerRecord` rows with `processed_at IS NULL`, which M1.106's own two-phase commit (trigger creation committed separately from the evaluation loop) can leave behind after a failed run — exactly the case `fail_execution` records.
- `get_event_driven_refresh_history` exposes the orchestration audit trail per stock.

**Testing:** `tests/test_event_intelligence_refresh.py`, 9 tests — successful run records completion, low-materiality event still completes with zero new triggers, duplicate `trigger_source` is a no-op even when a genuinely new event exists, a fresh `trigger_source` picks up that new event, concurrent execution for the same stock is rejected, a failure is recorded (`FAILED`, with reason) and re-raised, a failed run releases the lock so a retry with a new `trigger_source` succeeds, and backlog visibility (empty after success, surfaces an orphaned unprocessed row). Command: `DATABASE_URL="sqlite:///./test_scratch.db" python -m pytest tests/test_event_intelligence_refresh.py -q` → `9 passed`. Full suite: `1216 passed, 3 skipped, 3 deselected` (deselected: Postgres-only fresh-database migration tests, same as CI).

**Also fixed along the way (separate PR #231, unrelated to this EPIC's own scope but blocking anyone chaining a migration after M1.118):** EPIC-M1.118's migration revision id (`0097_event_schedule_orchestration`, 33 chars) exceeded `alembic_version.version_num`'s `VARCHAR(32)`, breaking fresh-database `alembic upgrade head`. Reported by `market-agent-m1-91`; fixed by renaming to `0097_event_sched_orchestration` (30 chars), no schema change.

**Not built (deliberately out of scope):** any new detection source beyond what M1.106 already ingests (news, corporate actions, price/volume shock, regime transitions) — "material market/sector movement" and "provider/data correction" event classes beyond what M1.106's existing thresholds already cover would need their own ingestion/detection EPIC, not a re-implementation here.
