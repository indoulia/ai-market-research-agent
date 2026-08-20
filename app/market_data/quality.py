from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DatasetValidationRun, MarketPrice

NSE_TIMEZONE = ZoneInfo("Asia/Kolkata")
RULESET_VERSION = "m1.2-v1"


@dataclass(frozen=True)
class PriceRecord:
    stock_id: int
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class ValidationIssue:
    rule: str
    stock_id: int
    session: str | None
    detail: str


@dataclass(frozen=True)
class ValidationReport:
    ruleset_version: str
    from_session: str
    to_session: str
    expected_sessions: tuple[str, ...]
    record_count: int
    issues: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict:
        return {
            "ruleset_version": self.ruleset_version,
            "from_session": self.from_session,
            "to_session": self.to_session,
            "expected_sessions": list(self.expected_sessions),
            "record_count": self.record_count,
            "issue_count": len(self.issues),
            "is_valid": self.is_valid,
            "issues": [asdict(issue) for issue in self.issues],
        }


def weekday_sessions(from_session: date, to_session: date) -> tuple[date, ...]:
    """Return weekday sessions; callers should pass an exchange calendar to account for holidays."""
    if from_session > to_session:
        raise ValueError("from_session must be on or before to_session")
    days = (to_session - from_session).days
    return tuple(
        from_session + timedelta(days=offset)
        for offset in range(days + 1)
        if (from_session + timedelta(days=offset)).weekday() < 5
    )


def validate_records(
    records: Iterable[PriceRecord],
    from_session: date,
    to_session: date,
    expected_sessions: Sequence[date] | None = None,
    stock_ids: Iterable[int] | None = None,
) -> ValidationReport:
    """Validate canonical daily OHLCV records using deterministic M1.2 rules."""
    if from_session > to_session:
        raise ValueError("from_session must be on or before to_session")
    rows = list(records)
    expected = tuple(expected_sessions) if expected_sessions is not None else weekday_sessions(from_session, to_session)
    expected_set = set(expected)
    if len(expected_set) != len(expected):
        raise ValueError("expected_sessions must not contain duplicates")
    if any(day < from_session or day > to_session for day in expected):
        raise ValueError("expected_sessions must fall within the validation range")

    issues: list[ValidationIssue] = []
    seen: set[tuple[int, datetime]] = set()
    observed: dict[int, set[date]] = {}
    requested_stocks = set(stock_ids or ())

    if not rows and not requested_stocks:
        issues.append(ValidationIssue("non_empty_dataset", 0, None, "validation range contains no records"))

    for row in rows:
        requested_stocks.add(row.stock_id)
        session = row.timestamp.astimezone(NSE_TIMEZONE).date() if row.timestamp.tzinfo else row.timestamp.date()
        session_text = session.isoformat()
        key = (row.stock_id, row.timestamp)
        if key in seen:
            issues.append(ValidationIssue("duplicate", row.stock_id, session_text, "duplicate stock_id/timestamp"))
        seen.add(key)
        observed.setdefault(row.stock_id, set()).add(session)

        prices = (row.open, row.high, row.low, row.close)
        if any(price <= 0 for price in prices):
            issues.append(ValidationIssue("positive_prices", row.stock_id, session_text, "OHLC prices must all be positive"))
        if row.volume <= 0:
            issues.append(ValidationIssue("positive_volume", row.stock_id, session_text, "volume must be positive"))
        if row.high < max(row.open, row.low, row.close):
            issues.append(ValidationIssue("ohlc_relationship", row.stock_id, session_text, "high must be the greatest OHLC value"))
        if row.low > min(row.open, row.high, row.close):
            issues.append(ValidationIssue("ohlc_relationship", row.stock_id, session_text, "low must be the least OHLC value"))
        if row.timestamp.tzinfo is None or row.timestamp.utcoffset() is None:
            issues.append(ValidationIssue("timestamp", row.stock_id, session_text, "timestamp must be timezone-aware"))
        elif row.timestamp.astimezone(NSE_TIMEZONE).time() != time.min:
            issues.append(ValidationIssue("timestamp", row.stock_id, session_text, "daily timestamp must be midnight in Asia/Kolkata"))
        if session not in expected_set:
            issues.append(ValidationIssue("unexpected_session", row.stock_id, session_text, "session is not in the expected trading calendar"))

    for stock_id in sorted(requested_stocks):
        for missing in sorted(expected_set - observed.get(stock_id, set())):
            issues.append(ValidationIssue("missing_session", stock_id, missing.isoformat(), "expected trading session is absent"))

    issues.sort(key=lambda issue: (issue.stock_id, issue.session or "", issue.rule, issue.detail))
    return ValidationReport(
        ruleset_version=RULESET_VERSION,
        from_session=from_session.isoformat(),
        to_session=to_session.isoformat(),
        expected_sessions=tuple(day.isoformat() for day in sorted(expected_set)),
        record_count=len(rows),
        issues=tuple(issues),
    )


def validate_market_prices(
    session: Session,
    from_session: date,
    to_session: date,
    stock_ids: Iterable[int] | None = None,
    expected_sessions: Sequence[date] | None = None,
) -> DatasetValidationRun:
    """Validate database records and persist the complete audit report."""
    selected_stock_ids = tuple(sorted(set(stock_ids or ())))
    start = datetime.combine(from_session, time.min, NSE_TIMEZONE)
    end = datetime.combine(to_session + timedelta(days=1), time.min, NSE_TIMEZONE)
    query = select(MarketPrice).where(MarketPrice.timestamp >= start, MarketPrice.timestamp < end)
    if selected_stock_ids:
        query = query.where(MarketPrice.stock_id.in_(selected_stock_ids))
    prices = session.scalars(query.order_by(MarketPrice.stock_id, MarketPrice.timestamp)).all()
    records = [
        PriceRecord(row.stock_id, row.timestamp, row.open, row.high, row.low, row.close, row.volume)
        for row in prices
    ]
    report = validate_records(records, from_session, to_session, expected_sessions, selected_stock_ids or None)
    run = DatasetValidationRun(
        from_timestamp=start,
        to_timestamp=end - timedelta(microseconds=1),
        status="PASSED" if report.is_valid else "FAILED",
        record_count=report.record_count,
        issue_count=len(report.issues),
        report_json=report.to_dict(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run
