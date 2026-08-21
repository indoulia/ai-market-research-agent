# EPIC-M1.118 — MRA Event & Schedule Orchestration

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
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
