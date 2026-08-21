# EPIC-M1.121 — Market Calendar & Operational Window Management

**Status:** VALIDATING (implemented, tests passing, PR open)
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

## Implementation

`app/market_calendar.py` supplies the canonical holiday/special-session data M1.118's `schedule_orchestration.classify_session` always accepted but never had a source for (M1.118's own docstring flagged this as an honest gap deferred to this EPIC):

- `MarketCalendarVersion` (versioned, provenance-tracked per exchange; `timezone_name` is data, not a hardcoded constant, so a future exchange needs no code change) + `MarketHoliday` + `MarketSpecialSession` + `MarketUnexpectedClosure` — all insert-only, idempotent-by-key.
- `register_calendar_version` rejects overlapping date ranges for the same exchange so `get_active_calendar_version` is always unambiguous.
- `get_holiday_dates`/`get_holiday_dates_in_range` produce the exact `holiday_dates` input `schedule_orchestration.classify_session`/`is_trading_session` already accept.
- `classify_operational_window` is the calendar-aware counterpart of `classify_session`: ordinary dates delegate straight to it; a registered special-session date has its own open/close (and optional pre/post-market) times fully replace the default window for that date. Raises `UnknownCalendarVersionError` (fails closed) if no calendar version covers the date.
- `count_trading_days` counts weekday/non-holiday dates in a half-open range for correct trading-day horizon counting.
- `is_market_open` is the calendar-aware convenience over `classify_operational_window`.

15 new tests in `tests/test_market_calendar.py`; migration `0099_market_calendar` adds the four tables.
