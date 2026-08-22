"""EPIC-M1.121: authoritative market-session and calendar awareness, so
every MRA operation runs in the correct trading context.

M1.118's `schedule_orchestration.classify_session` already correctly
implements NSE's weekday/pre-market/open/close/post-market window
classification, using `zoneinfo` rather than a hardcoded offset -- it only
ever lacked a canonical holiday list of its own (its own docstring: "this
module carries no canonical NSE holiday calendar of its own ... M1.121 ...
is the future EPIC responsible for supplying that authoritative list").
This module supplies exactly that, reusing `classify_session` for the
ordinary case rather than reimplementing session-window logic a second
time, and adds the one case M1.118 genuinely could not handle: a special
session (e.g. Muhurat trading) whose own open/close times fully replace
the default window for that one calendar date.

**Versioned, provenance-tracked calendars** (scope: "preserve calendar
source/provider provenance and version"): `MarketCalendarVersion` records
which authority (`source`) published a calendar, for which date range
(`effective_from`/`effective_to`), in which timezone -- `timezone_name` is
data on the calendar version, not a hardcoded module constant, so a future
exchange in a different timezone (scope: "support future market expansion
without embedding exchange-specific rules in business logic") is just
another registered `MarketCalendarVersion` row, never a code change.
`register_calendar_version` rejects two versions for the same exchange
with overlapping date ranges (`OverlappingCalendarVersionError`) so
`get_active_calendar_version` is always unambiguous (AC: "holiday and
special-session behavior is deterministic").

**Immutable, auditable history** (AC: "calendar changes are auditable and
do not rewrite historical outcomes"): every row here is insert-only --
`register_calendar_version`/`record_holiday`/`record_special_session`/
`record_unexpected_closure` are all idempotent-by-key and never update an
existing row's substantive fields; a calendar correction is always a new
version or a new dated record, never an edit of history. This module also
never writes to `Prediction`/`PredictionOutcome` -- same propose-only
posture as every other gate/decision module in this platform.

**Unexpected closures** (scope: "handle unexpected closures and session
changes"): `MarketUnexpectedClosure` is a separate, exchange-scoped,
same-day-announceable log -- it does not require amending a published
`MarketCalendarVersion` (which is aspirational/published-in-advance) to
react to a genuinely ad-hoc closure.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import MarketCalendarVersion, MarketHoliday, MarketSpecialSession, MarketUnexpectedClosure
from .schedule_orchestration import SESSION_CLOSED, SESSION_MARKET_HOURS, SESSION_POST_MARKET, SESSION_PRE_MARKET, classify_session

MARKET_CALENDAR_VERSION = "MCL-001"

UNEXPECTED_CLOSURE_SOURCE_DEFAULT = "MANUAL_OVERRIDE"


class CalendarVersionRedefinitionError(RuntimeError):
    """A registered calendar version's bounds can never be changed."""


class OverlappingCalendarVersionError(RuntimeError):
    """Two calendar versions for the same exchange must never have
    overlapping effective date ranges -- otherwise which one is
    authoritative for a given date would be ambiguous."""


class UnknownCalendarVersionError(RuntimeError):
    """Raised when no calendar version is registered for the exchange as
    of the date in question -- fails closed rather than guessing."""


class SpecialSessionConflictError(RuntimeError):
    """A date cannot be both a holiday and a special session."""


def _date_ranges_overlap(a_start: date, a_end: date | None, b_start: date, b_end: date | None) -> bool:
    if a_end is not None and b_start > a_end:
        return False
    if b_end is not None and a_start > b_end:
        return False
    return True


def register_calendar_version(
    session: Session,
    *,
    exchange: str,
    version_label: str,
    source: str,
    timezone_name: str,
    effective_from: date,
    effective_to: date | None,
    published_at: datetime,
) -> MarketCalendarVersion:
    """Idempotent by `(exchange, version_label)`: re-registering identical
    bounds/timezone/source is a no-op; attempting to redefine an existing
    label's bounds, timezone or source raises. Rejects any bounds that
    overlap a *different* already-registered version for this exchange
    (AC: "holiday and special-session behavior is deterministic")."""
    existing = session.scalar(
        select(MarketCalendarVersion).where(
            MarketCalendarVersion.exchange == exchange, MarketCalendarVersion.version_label == version_label
        )
    )
    if existing is not None:
        if (
            existing.source != source
            or existing.timezone_name != timezone_name
            or existing.effective_from != effective_from
            or existing.effective_to != effective_to
        ):
            raise CalendarVersionRedefinitionError(
                f"calendar version '{version_label}' for {exchange} is already registered with different bounds"
            )
        return existing

    others = session.scalars(select(MarketCalendarVersion).where(MarketCalendarVersion.exchange == exchange)).all()
    for other in others:
        if _date_ranges_overlap(effective_from, effective_to, other.effective_from, other.effective_to):
            raise OverlappingCalendarVersionError(
                f"calendar version '{version_label}' overlaps existing version '{other.version_label}' for {exchange}"
            )

    version = MarketCalendarVersion(
        exchange=exchange, version_label=version_label, source=source, timezone_name=timezone_name,
        effective_from=effective_from, effective_to=effective_to, published_at=published_at,
        calendar_rule_version=MARKET_CALENDAR_VERSION,
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    return version


def get_active_calendar_version(session: Session, exchange: str, *, as_of: date) -> MarketCalendarVersion | None:
    return session.scalar(
        select(MarketCalendarVersion).where(
            MarketCalendarVersion.exchange == exchange,
            MarketCalendarVersion.effective_from <= as_of,
            or_(MarketCalendarVersion.effective_to.is_(None), MarketCalendarVersion.effective_to >= as_of),
        )
    )


def get_calendar_version_history(session: Session, exchange: str) -> tuple[MarketCalendarVersion, ...]:
    return tuple(
        session.scalars(
            select(MarketCalendarVersion)
            .where(MarketCalendarVersion.exchange == exchange)
            .order_by(MarketCalendarVersion.effective_from.asc())
        ).all()
    )


def record_holiday(
    session: Session, *, calendar_version_id: int, holiday_date: date, description: str
) -> MarketHoliday:
    existing = session.scalar(
        select(MarketHoliday).where(
            MarketHoliday.calendar_version_id == calendar_version_id, MarketHoliday.holiday_date == holiday_date
        )
    )
    if existing is not None:
        return existing

    holiday = MarketHoliday(calendar_version_id=calendar_version_id, holiday_date=holiday_date, description=description)
    session.add(holiday)
    session.commit()
    session.refresh(holiday)
    return holiday


def get_holidays(session: Session, calendar_version_id: int) -> tuple[MarketHoliday, ...]:
    return tuple(
        session.scalars(
            select(MarketHoliday)
            .where(MarketHoliday.calendar_version_id == calendar_version_id)
            .order_by(MarketHoliday.holiday_date.asc())
        ).all()
    )


def record_special_session(
    session: Session,
    *,
    calendar_version_id: int,
    session_date: date,
    open_time,
    close_time,
    description: str,
    pre_market_start=None,
    post_market_end=None,
) -> MarketSpecialSession:
    """Idempotent by `(calendar_version_id, session_date)`. Raises
    `SpecialSessionConflictError` if `session_date` is already recorded as
    a holiday for this calendar version -- a date cannot be both."""
    existing = session.scalar(
        select(MarketSpecialSession).where(
            MarketSpecialSession.calendar_version_id == calendar_version_id,
            MarketSpecialSession.session_date == session_date,
        )
    )
    if existing is not None:
        return existing

    conflicting_holiday = session.scalar(
        select(MarketHoliday).where(
            MarketHoliday.calendar_version_id == calendar_version_id, MarketHoliday.holiday_date == session_date
        )
    )
    if conflicting_holiday is not None:
        raise SpecialSessionConflictError(
            f"{session_date} is already recorded as a holiday for calendar version {calendar_version_id}"
        )

    special = MarketSpecialSession(
        calendar_version_id=calendar_version_id, session_date=session_date, pre_market_start=pre_market_start,
        open_time=open_time, close_time=close_time, post_market_end=post_market_end, description=description,
    )
    session.add(special)
    session.commit()
    session.refresh(special)
    return special


def get_special_sessions(session: Session, calendar_version_id: int) -> tuple[MarketSpecialSession, ...]:
    return tuple(
        session.scalars(
            select(MarketSpecialSession)
            .where(MarketSpecialSession.calendar_version_id == calendar_version_id)
            .order_by(MarketSpecialSession.session_date.asc())
        ).all()
    )


def record_unexpected_closure(
    session: Session, *, exchange: str, closure_date: date, reason: str, recorded_at: datetime,
    source: str = UNEXPECTED_CLOSURE_SOURCE_DEFAULT,
) -> MarketUnexpectedClosure:
    """Idempotent by `(exchange, closure_date)`. A separate, same-day-
    announceable log distinct from `MarketCalendarVersion` -- an
    unexpected closure does not require amending a published calendar
    (scope: "handle unexpected closures and session changes")."""
    existing = session.scalar(
        select(MarketUnexpectedClosure).where(
            MarketUnexpectedClosure.exchange == exchange, MarketUnexpectedClosure.closure_date == closure_date
        )
    )
    if existing is not None:
        return existing

    closure = MarketUnexpectedClosure(
        exchange=exchange, closure_date=closure_date, reason=reason, source=source, recorded_at=recorded_at,
    )
    session.add(closure)
    session.commit()
    session.refresh(closure)
    return closure


def get_unexpected_closures(session: Session, exchange: str) -> tuple[MarketUnexpectedClosure, ...]:
    return tuple(
        session.scalars(
            select(MarketUnexpectedClosure)
            .where(MarketUnexpectedClosure.exchange == exchange)
            .order_by(MarketUnexpectedClosure.closure_date.asc())
        ).all()
    )


def get_holiday_dates_in_range(session: Session, exchange: str, start_date: date, end_date: date) -> frozenset[date]:
    """Union of every registered holiday (across every calendar version
    whose effective range intersects `[start_date, end_date)`) and every
    unexpected closure in that range -- the canonical `holiday_dates`
    input M1.118's `classify_session`/`is_trading_session` already accept
    (scope: "expose operational-window queries to orchestration")."""
    versions = session.scalars(
        select(MarketCalendarVersion).where(
            MarketCalendarVersion.exchange == exchange,
            MarketCalendarVersion.effective_from < end_date,
            or_(MarketCalendarVersion.effective_to.is_(None), MarketCalendarVersion.effective_to >= start_date),
        )
    ).all()

    holiday_dates: set[date] = set()
    if versions:
        version_ids = [v.id for v in versions]
        holiday_dates.update(
            session.scalars(select(MarketHoliday.holiday_date).where(MarketHoliday.calendar_version_id.in_(version_ids))).all()
        )

    holiday_dates.update(
        session.scalars(
            select(MarketUnexpectedClosure.closure_date).where(
                MarketUnexpectedClosure.exchange == exchange,
                MarketUnexpectedClosure.closure_date >= start_date,
                MarketUnexpectedClosure.closure_date < end_date,
            )
        ).all()
    )
    return frozenset(d for d in holiday_dates if start_date <= d < end_date)


def get_holiday_dates(session: Session, exchange: str, *, as_of: date) -> frozenset[date]:
    return get_holiday_dates_in_range(session, exchange, as_of, as_of + timedelta(days=1))


def count_trading_days(session: Session, exchange: str, start_date: date, end_date: date) -> int:
    """Counts weekday, non-holiday dates in the half-open range
    `[start_date, end_date)` -- half-open so a horizon of N trading days
    from `start_date` lands exactly N trading days later (AC: "prediction
    horizons count trading days correctly")."""
    if end_date < start_date:
        raise ValueError("end_date must not be before start_date")

    holiday_dates = get_holiday_dates_in_range(session, exchange, start_date, end_date)
    count = 0
    current = start_date
    while current < end_date:
        if current.weekday() < 5 and current not in holiday_dates:
            count += 1
        current += timedelta(days=1)
    return count


@dataclass(frozen=True)
class OperationalWindow:
    exchange: str
    at: datetime
    market_session: str
    is_special_session: bool
    calendar_version_label: str
    special_session_description: str | None


def _classify_with_special_session_times(local_time, special: MarketSpecialSession) -> str:
    if special.pre_market_start is not None and special.pre_market_start <= local_time < special.open_time:
        return SESSION_PRE_MARKET
    if special.open_time <= local_time < special.close_time:
        return SESSION_MARKET_HOURS
    if special.post_market_end is not None and special.close_time <= local_time < special.post_market_end:
        return SESSION_POST_MARKET
    return SESSION_CLOSED


def classify_operational_window(session: Session, exchange: str, at: datetime) -> OperationalWindow:
    """The calendar-aware counterpart of M1.118's `classify_session`.
    Raises `UnknownCalendarVersionError` (fails closed) if no calendar
    version covers `at`'s date for `exchange`. On an ordinary date,
    delegates straight to `classify_session` with this module's
    authoritative holiday set. On a registered special-session date, the
    special session's own open/close (and optional pre/post-market) times
    fully replace the default window for that date -- they do not extend
    it (AC: "holiday and special-session behavior is deterministic")."""
    aware_at = at if at.tzinfo is not None else at.replace(tzinfo=ZoneInfo("UTC"))
    utc_date = aware_at.astimezone(ZoneInfo("UTC")).date()

    version = get_active_calendar_version(session, exchange, as_of=utc_date)
    if version is None:
        raise UnknownCalendarVersionError(f"no active calendar version registered for exchange={exchange!r} as of {utc_date}")

    local_at = aware_at.astimezone(ZoneInfo(version.timezone_name))
    local_date = local_at.date()

    special = session.scalar(
        select(MarketSpecialSession).where(
            MarketSpecialSession.calendar_version_id == version.id, MarketSpecialSession.session_date == local_date
        )
    )
    if special is not None:
        market_session = _classify_with_special_session_times(local_at.time(), special)
        return OperationalWindow(
            exchange=exchange, at=at, market_session=market_session, is_special_session=True,
            calendar_version_label=version.version_label, special_session_description=special.description,
        )

    holiday_dates = get_holiday_dates(session, exchange, as_of=local_date)
    market_session = classify_session(aware_at, holiday_dates=holiday_dates)
    return OperationalWindow(
        exchange=exchange, at=at, market_session=market_session, is_special_session=False,
        calendar_version_label=version.version_label, special_session_description=None,
    )


def is_market_open(session: Session, exchange: str, at: datetime) -> bool:
    return classify_operational_window(session, exchange, at).market_session == SESSION_MARKET_HOURS


class NoTradingDayFoundError(RuntimeError):
    """Raised when no trading day is found within the bounded lookback
    window -- fails closed (same posture as `UnknownCalendarVersionError`)
    rather than looping forever or silently returning a non-trading date."""


def last_trading_day_on_or_before(
    session: Session, exchange: str, as_of: date, *, lookback_days: int = 14
) -> date:
    """Walks backward from `as_of` (inclusive), skipping weekends and every
    registered holiday/unexpected closure for `exchange`, and returns the
    first real trading day found. This is the calendar-aware counterpart
    any "default to today" caller needs: without it, a caller that defaults
    an unspecified scan/report date to a raw calendar date silently lands on
    a non-trading day whenever "today" is a weekend or a weekday NSE holiday
    -- and every downstream staleness check that expects the latest ingested
    session to be `>= that date` then fails, even though the most recent
    real session's data is fully fresh (the exact discovery-scan bug this
    function exists to fix: `scripts/run_discovery_scan.py` defaulting
    `--scan-date` to today's raw date on a weekend/holiday cron run).

    Bounded by `lookback_days` (default 14, comfortably more than any
    realistic NSE holiday cluster) rather than scanning backward forever;
    raises `NoTradingDayFoundError` if no trading day is found in that
    window, since a caller silently getting an arbitrary/wrong date back
    here would be worse than failing loudly."""
    window_start = as_of - timedelta(days=lookback_days)
    holiday_dates = get_holiday_dates_in_range(session, exchange, window_start, as_of + timedelta(days=1))

    current = as_of
    while current >= window_start:
        if current.weekday() < 5 and current not in holiday_dates:
            return current
        current -= timedelta(days=1)

    raise NoTradingDayFoundError(
        f"no trading day found for exchange={exchange!r} within {lookback_days} days on or before {as_of.isoformat()}"
    )
