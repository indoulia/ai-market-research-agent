# EPIC-M1.35 — Automatic Information Refresh Policy

**Status:** READY_FOR_APPROVAL
**Execution Status:** NOT_STARTED
**Priority:** P1

## Objective
Determine what information must be fetched, when it must be refreshed, and when existing data is sufficiently fresh for analysis.

## Scope
- Define freshness requirements by data type.
- Define market-data refresh cadence.
- Define news/event refresh triggers.
- Define fundamental-data refresh rules.
- Track source timestamp and fetch timestamp.
- Detect stale or missing data before analysis.
- Avoid unnecessary duplicate fetches.
- Record refresh failures explicitly.

## Acceptance Criteria
- [ ] Each supported data type has a defined freshness policy.
- [ ] Analysis can determine whether required data is fresh enough.
- [ ] Stale data triggers refresh or explicit non-qualification.
- [ ] Fetch attempts and failures are auditable.
- [ ] Duplicate unnecessary fetches are avoided.
- [ ] Historical snapshots used by recommendations remain immutable.

## Dependencies
**Previous:** M1.34
**Next:** M1.36

## Completion Report
Claude must document freshness rules, scheduler/trigger behavior, failure handling, tests, and evidence.