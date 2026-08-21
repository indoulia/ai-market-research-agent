# EPIC-M1.121 — Market Calendar & Operational Window Management

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Provide authoritative market-session and calendar awareness so every MRA operation runs in the correct trading context.

## Scope
- Model trading days, holidays, sessions and special sessions.
- Support pre-market, open, continuous session, close and post-market windows.
- Prevent price-monitoring logic from treating non-trading periods as normal market time.
- Handle unexpected closures and session changes.
- Expose operational-window queries to orchestration and outcome monitoring.
- Preserve calendar source/provider provenance and version.
- Support future market expansion without embedding exchange-specific rules in business logic.

## Acceptance Criteria
- Scheduling respects the authoritative configured market calendar.
- Holiday and special-session behavior is deterministic.
- Prediction horizons count trading days correctly.
- Target/SL monitoring operates only in appropriate market windows unless explicit policy says otherwise.
- Calendar changes are auditable and do not rewrite historical outcomes.

## Dependencies
M1.95, M1.118.

## Architectural Rule
**Market-calendar logic is a capability/provider concern exposed through a stable contract; business logic must not hard-code exchange calendars.**
