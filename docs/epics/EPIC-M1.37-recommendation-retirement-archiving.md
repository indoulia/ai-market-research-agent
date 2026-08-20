# EPIC-M1.37 — Recommendation Retirement & Archiving

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P1

## Objective
Automatically close recommendations when their lifecycle ends and archive historical records without deleting evidence.

## Scope
- Define active, completed, retired, and archived states.
- Retire recommendations at deterministic horizon completion.
- Prevent expired recommendations from appearing as active.
- Define archive eligibility and retention metadata.
- Keep archived records queryable.
- Never delete recommendation evidence as part of normal retirement.

## Acceptance Criteria
- [ ] Recommendations retire automatically at the correct horizon.
- [ ] Retirement is immutable and auditable.
- [ ] Archived records retain complete provenance and outcomes.
- [ ] Active views exclude retired/archived recommendations.
- [ ] Archive operations are idempotent.
- [ ] No evidence is lost through lifecycle transitions.

## Dependencies
**Previous:** M1.36
**Next:** M1.38

## Completion Report
Claude must document state transitions, retention rules, tests, and evidence that archived history remains recoverable.