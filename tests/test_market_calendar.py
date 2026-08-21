from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.market_calendar import (
    MARKET_CALENDAR_VERSION,
    CalendarVersionRedefinitionError,
    OverlappingCalendarVersionError,
    SpecialSessionConflictError,
    UnknownCalendarVersionError,
    classify_operational_window,
    count_trading_days,
    get_active_calendar_version,
    get_calendar_version_history,
    get_holiday_dates,
    get_holiday_dates_in_range,
    is_market_open,
    record_holiday,
    record_special_session,
    record_unexpected_closure,
    register_calendar_version,
)
from app.schedule_orchestration import SESSION_CLOSED, SESSION_MARKET_HOURS, SESSION_POST_MARKET, SESSION_PRE_MARKET

EXCHANGE = "NSE"
IST = "Asia/Kolkata"
PUBLISHED_AT = datetime(2027, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _register_2027(session, *, effective_to=None):
    return register_calendar_version(
        session, exchange=EXCHANGE, version_label="2027", source="NSE_CIRCULAR_2027",
        timezone_name=IST, effective_from=date(2027, 1, 1), effective_to=effective_to,
        published_at=PUBLISHED_AT,
    )


def _ist(y, m, d, hh, mm):
    # naive-UTC-by-convention timestamp equal to the given IST wall-clock time
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc) - timedelta(hours=5, minutes=30)


def test_register_calendar_version_idempotent_and_rejects_redefinition(session):
    first = _register_2027(session)
    second = _register_2027(session)
    assert first.id == second.id
    assert first.calendar_rule_version == MARKET_CALENDAR_VERSION

    with pytest.raises(CalendarVersionRedefinitionError):
        register_calendar_version(
            session, exchange=EXCHANGE, version_label="2027", source="NSE_CIRCULAR_2027",
            timezone_name=IST, effective_from=date(2027, 1, 2), effective_to=None, published_at=PUBLISHED_AT,
        )


def test_register_calendar_version_rejects_overlap(session):
    _register_2027(session, effective_to=date(2027, 12, 31))

    with pytest.raises(OverlappingCalendarVersionError):
        register_calendar_version(
            session, exchange=EXCHANGE, version_label="2027-amendment", source="NSE_CIRCULAR_2027B",
            timezone_name=IST, effective_from=date(2027, 6, 1), effective_to=None, published_at=PUBLISHED_AT,
        )


def test_get_active_calendar_version_open_ended(session):
    version = _register_2027(session)
    assert get_active_calendar_version(session, EXCHANGE, as_of=date(2027, 6, 15)).id == version.id
    assert get_active_calendar_version(session, EXCHANGE, as_of=date(2026, 12, 31)) is None


def test_get_calendar_version_history(session):
    _register_2027(session, effective_to=date(2027, 12, 31))
    register_calendar_version(
        session, exchange=EXCHANGE, version_label="2028", source="NSE_CIRCULAR_2028",
        timezone_name=IST, effective_from=date(2028, 1, 1), effective_to=None, published_at=PUBLISHED_AT,
    )
    history = get_calendar_version_history(session, EXCHANGE)
    assert [v.version_label for v in history] == ["2027", "2028"]


def test_record_holiday_idempotent(session):
    version = _register_2027(session)
    first = record_holiday(session, calendar_version_id=version.id, holiday_date=date(2027, 1, 26), description="Republic Day")
    second = record_holiday(session, calendar_version_id=version.id, holiday_date=date(2027, 1, 26), description="Republic Day")
    assert first.id == second.id


def test_get_holiday_dates_includes_unexpected_closures(session):
    version = _register_2027(session)
    record_holiday(session, calendar_version_id=version.id, holiday_date=date(2027, 1, 26), description="Republic Day")
    record_unexpected_closure(session, exchange=EXCHANGE, closure_date=date(2027, 3, 10), reason="exchange outage", recorded_at=PUBLISHED_AT)

    dates = get_holiday_dates(session, EXCHANGE, as_of=date(2027, 1, 26))
    assert date(2027, 1, 26) in dates

    dates_range = get_holiday_dates_in_range(session, EXCHANGE, date(2027, 1, 1), date(2027, 4, 1))
    assert {date(2027, 1, 26), date(2027, 3, 10)} <= dates_range


def test_record_special_session_conflicts_with_holiday(session):
    version = _register_2027(session)
    record_holiday(session, calendar_version_id=version.id, holiday_date=date(2027, 11, 5), description="Diwali")

    with pytest.raises(SpecialSessionConflictError):
        record_special_session(
            session, calendar_version_id=version.id, session_date=date(2027, 11, 5),
            open_time=time(18, 0), close_time=time(19, 0), description="Muhurat trading",
        )


def test_classify_operational_window_ordinary_trading_hours(session):
    _register_2027(session)
    at = _ist(2027, 6, 15, 10, 0)  # Tuesday, 10:00 IST
    window = classify_operational_window(session, EXCHANGE, at)
    assert window.market_session == SESSION_MARKET_HOURS
    assert window.is_special_session is False
    assert window.calendar_version_label == "2027"


def test_classify_operational_window_respects_registered_holiday(session):
    version = _register_2027(session)
    record_holiday(session, calendar_version_id=version.id, holiday_date=date(2027, 1, 26), description="Republic Day")

    at = _ist(2027, 1, 26, 10, 0)  # would be market hours if not a holiday
    window = classify_operational_window(session, EXCHANGE, at)
    assert window.market_session == SESSION_CLOSED


def test_classify_operational_window_uses_special_session_times(session):
    version = _register_2027(session)
    record_special_session(
        session, calendar_version_id=version.id, session_date=date(2027, 11, 5),
        open_time=time(18, 0), close_time=time(19, 0), description="Muhurat trading",
    )

    during = _ist(2027, 11, 5, 18, 30)
    window = classify_operational_window(session, EXCHANGE, during)
    assert window.market_session == SESSION_MARKET_HOURS
    assert window.is_special_session is True
    assert window.special_session_description == "Muhurat trading"

    # ordinary daytime NSE hours (9:15-15:30) are NOT trading hours on a
    # special-session day -- the special session's own times fully replace
    # the default window, they don't add to it.
    ordinary_hours = _ist(2027, 11, 5, 10, 0)
    ordinary_window = classify_operational_window(session, EXCHANGE, ordinary_hours)
    assert ordinary_window.market_session == SESSION_CLOSED


def test_classify_operational_window_raises_without_registered_calendar(session):
    with pytest.raises(UnknownCalendarVersionError):
        classify_operational_window(session, EXCHANGE, _ist(2027, 6, 15, 10, 0))


def test_is_market_open(session):
    _register_2027(session)
    assert is_market_open(session, EXCHANGE, _ist(2027, 6, 15, 10, 0)) is True
    assert is_market_open(session, EXCHANGE, _ist(2027, 6, 15, 20, 0)) is False
    assert is_market_open(session, EXCHANGE, _ist(2027, 6, 19, 10, 0)) is False  # Saturday


def test_count_trading_days_excludes_weekends_and_holidays(session):
    version = _register_2027(session)
    record_holiday(session, calendar_version_id=version.id, holiday_date=date(2027, 1, 26), description="Republic Day")

    # 2027-01-25 (Mon) through 2027-01-30 (Sat), half-open [start, end)
    # weekdays: 25,26,27,28,29 -- 26 is a holiday -> 4 trading days
    count = count_trading_days(session, EXCHANGE, date(2027, 1, 25), date(2027, 1, 30))
    assert count == 4


def test_count_trading_days_rejects_end_before_start(session):
    with pytest.raises(ValueError):
        count_trading_days(session, EXCHANGE, date(2027, 1, 30), date(2027, 1, 25))


def test_record_unexpected_closure_idempotent_and_immutable_log(session):
    first = record_unexpected_closure(session, exchange=EXCHANGE, closure_date=date(2027, 3, 10), reason="exchange outage", recorded_at=PUBLISHED_AT)
    second = record_unexpected_closure(session, exchange=EXCHANGE, closure_date=date(2027, 3, 10), reason="exchange outage", recorded_at=PUBLISHED_AT)
    assert first.id == second.id
