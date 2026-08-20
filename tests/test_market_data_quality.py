from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.market_data.quality import PriceRecord, validate_records

NSE = ZoneInfo("Asia/Kolkata")


def record(day: int, *, stock_id: int = 1, **overrides) -> PriceRecord:
    values = {
        "stock_id": stock_id,
        "timestamp": datetime(2026, 8, day, tzinfo=NSE),
        "open": Decimal("100"),
        "high": Decimal("110"),
        "low": Decimal("90"),
        "close": Decimal("105"),
        "volume": 1000,
    }
    values.update(overrides)
    return PriceRecord(**values)


def test_valid_dataset_provides_passing_gate():
    report = validate_records([record(17), record(18), record(19)], date(2026, 8, 17), date(2026, 8, 19))
    assert report.is_valid
    assert report.to_dict()["issue_count"] == 0


def test_detects_invalid_ohlcv_duplicate_and_timestamp():
    bad = record(
        17,
        open=Decimal("0"),
        high=Decimal("99"),
        low=Decimal("106"),
        close=Decimal("105"),
        volume=0,
        timestamp=datetime(2026, 8, 17, 1, tzinfo=NSE),
    )
    report = validate_records([bad, bad], date(2026, 8, 17), date(2026, 8, 17))
    rules = {issue.rule for issue in report.issues}
    assert not report.is_valid
    assert {"positive_prices", "positive_volume", "ohlc_relationship", "timestamp", "duplicate"} <= rules


def test_reports_missing_sessions_for_each_requested_stock():
    report = validate_records(
        [record(17)],
        date(2026, 8, 17),
        date(2026, 8, 18),
        stock_ids=[1, 2],
    )
    missing = {(issue.stock_id, issue.session) for issue in report.issues if issue.rule == "missing_session"}
    assert missing == {(1, "2026-08-18"), (2, "2026-08-17"), (2, "2026-08-18")}


def test_custom_exchange_calendar_avoids_false_holiday_gap():
    report = validate_records(
        [record(17), record(19)],
        date(2026, 8, 17),
        date(2026, 8, 19),
        expected_sessions=[date(2026, 8, 17), date(2026, 8, 19)],
    )
    assert report.is_valid


def test_rejects_invalid_validation_range():
    with pytest.raises(ValueError, match="on or before"):
        validate_records([], date(2026, 8, 19), date(2026, 8, 17))


def test_empty_unscoped_dataset_fails_closed():
    report = validate_records([], date(2026, 8, 17), date(2026, 8, 17))
    assert not report.is_valid
    assert report.issues[0].rule == "non_empty_dataset"
