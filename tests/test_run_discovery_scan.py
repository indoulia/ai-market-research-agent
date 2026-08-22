"""EPIC-M1.149: cover the operational entrypoint itself -- CLI argument
parsing, SignalProvider resolution/failure, and `run_scan`'s persistence,
empty-data, and idempotency behavior -- on top of `app.continuous_discovery`,
which already has its own test coverage for the pipeline it composes."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.discovery import SOURCE_DAILY_UNIVERSE_SCAN
from app.market_calendar import register_calendar_version
from app.market_data.quality import NSE_TIMEZONE
from app.models import DiscoveryRecord, MarketPrice, ScanCandidate, Stock
from app.baseline_signal import BaselineSignalProvider
from app.scan import CandidateSignals
from scripts.run_discovery_scan import (
    DiscoveryScanConfigurationError,
    _parse_args,
    _resolve_signal_provider,
    run_scan,
)
import scripts.run_discovery_scan as run_discovery_scan_module

SCAN_DATE = date(2026, 8, 20)
AS_OF = datetime(2026, 8, 20, tzinfo=timezone.utc)


class StubSignalProvider:
    model_version = "test-model-1"

    def __init__(self, predicted_probability=Decimal("0.65"), confidence=Decimal("0.70")):
        self._predicted_probability = predicted_probability
        self._confidence = confidence

    def predict(self, stock_id, features):
        return CandidateSignals(predicted_probability=self._predicted_probability, confidence=self._confidence)


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


def _make_stock(session, symbol="RELIANCE"):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=True)
    session.add(stock)
    session.flush()
    return stock


def _make_rising_price_history(session, stock_id, last_session=SCAN_DATE, count=25, base_price=Decimal("100")):
    for offset in range(count):
        session_date = last_session - timedelta(days=count - 1 - offset)
        timestamp = datetime.combine(session_date, time.min, NSE_TIMEZONE)
        price = base_price + Decimal(offset)
        session.add(
            MarketPrice(
                stock_id=stock_id,
                timestamp=timestamp,
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price,
                volume=10_000,
                source="test",
            )
        )
    session.flush()


def _run_scan_kwargs(**overrides):
    kwargs = dict(
        scan_date=SCAN_DATE,
        as_of=AS_OF,
        signal_provider=StubSignalProvider(),
        target_return=Decimal("0.05"),
        stop_return=Decimal("-0.03"),
        min_score=Decimal("0"),
        provider_name="test-provider",
    )
    kwargs.update(overrides)
    return kwargs


# ---- provider resolution ----


def test_resolve_signal_provider_baseline():
    provider = _resolve_signal_provider("baseline")
    assert isinstance(provider, BaselineSignalProvider)
    assert provider.model_version == "BASELINE-001"


def test_resolve_signal_provider_unknown_fails_loudly():
    with pytest.raises(SystemExit) as excinfo:
        _resolve_signal_provider("chatgpt-o5")
    assert isinstance(excinfo.value, DiscoveryScanConfigurationError)
    assert "chatgpt-o5" in str(excinfo.value)


# ---- CLI argument parsing ----


def test_parse_args_defaults():
    args = _parse_args([])
    assert args.scan_date is None
    assert args.as_of is None
    assert args.target_return == Decimal("0.05")
    assert args.stop_return == Decimal("-0.03")


def test_parse_args_overrides():
    args = _parse_args(
        ["--scan-date", "2026-08-21", "--target-return", "0.08", "--stop-return", "-0.04", "--daily-limit", "3"]
    )
    assert args.scan_date == date(2026, 8, 21)
    assert args.target_return == Decimal("0.08")
    assert args.stop_return == Decimal("-0.04")
    assert args.daily_limit == 3


# ---- run_scan: persistence, empty data, idempotency ----


def test_run_scan_persists_real_candidates_and_discoveries(session):
    stock = _make_stock(session)
    _make_rising_price_history(session, stock.id)

    summary = run_scan(session, **_run_scan_kwargs())

    assert summary["status"] == "ok"
    assert summary["active_stocks"] == 1
    assert summary["input_market_price_rows"] == 25
    assert summary["candidates_eligible"] == 1
    assert summary["candidates_excluded"] == 0
    assert summary["discovery_records_created"] == 1
    assert summary["recommendation_generations_created"] == 1
    assert summary["recommendations_selected"] == 1
    assert summary["signal_provider"] == "test-provider"

    discovery = session.scalar(select(DiscoveryRecord).where(DiscoveryRecord.stock_id == stock.id))
    assert discovery.source == SOURCE_DAILY_UNIVERSE_SCAN


def test_run_scan_with_no_market_data_reports_explicit_zero_result(session):
    # No stocks, no prices at all -- must report cleanly, not raise.
    summary = run_scan(session, **_run_scan_kwargs())

    assert summary["status"] == "no_market_data"
    assert summary["active_stocks"] == 0
    assert summary["input_market_price_rows"] == 0
    assert summary["candidates_eligible"] == 0
    assert summary["discovery_records_created"] == 0


def test_run_scan_excluded_candidate_reports_reason(session):
    _make_stock(session)  # active stock, zero price history -> missing_market_data

    summary = run_scan(session, **_run_scan_kwargs())

    assert summary["candidates_excluded"] == 1
    assert summary["candidates_excluded_by_reason"] == {"missing_market_data": 1}
    # still gets a provenance row even though it was excluded
    assert summary["discovery_records_created"] == 1


def test_run_scan_is_idempotent_for_the_same_scan_date(session):
    stock = _make_stock(session)
    _make_rising_price_history(session, stock.id)

    first = run_scan(session, **_run_scan_kwargs())
    second = run_scan(session, **_run_scan_kwargs())

    assert first == second
    assert session.query(ScanCandidate).count() == 1
    assert session.query(DiscoveryRecord).count() == 1


def test_run_scan_unresolvable_entry_price_fails_loudly(session, monkeypatch):
    stock = _make_stock(session)
    _make_rising_price_history(session, stock.id)
    # Force the "should never happen" branch to prove it fails loudly instead
    # of silently fabricating a price.
    import scripts.run_discovery_scan as module

    monkeypatch.setattr(module, "_latest_close_prices_by_stock", lambda session, cutoff: {})

    with pytest.raises(SystemExit):
        run_scan(session, **_run_scan_kwargs())


# ---- run(): default scan-date resolution must never land on a
# weekend/holiday (regression test for the real bug found while validating
# a live Rancher/k3s deployment: a weekend/holiday cron run with no
# --scan-date defaulted to today's raw calendar date and every candidate
# was wrongly excluded as stale_market_data even though the last real
# session's data was fully fresh) ----


class _FrozenDateTime(datetime):
    """Subclassing (rather than replacing) `datetime` so every other
    classmethod (`combine`, `fromisoformat`, ...) `scripts.run_discovery_scan`
    relies on keeps working unchanged -- only `now()` is frozen."""

    _frozen_now: datetime

    @classmethod
    def now(cls, tz=None):
        return cls._frozen_now.astimezone(tz) if tz is not None else cls._frozen_now


def test_run_defaults_scan_date_to_last_trading_day_when_today_is_a_weekend(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    friday = date(2027, 1, 22)  # last real NSE trading day
    saturday = date(2027, 1, 23)  # "today" -- no candle can ever exist for it

    setup_session = TestSessionLocal()
    try:
        register_calendar_version(
            setup_session, exchange="NSE", version_label="2027", source="NSE_CIRCULAR_2027",
            timezone_name="Asia/Kolkata", effective_from=date(2027, 1, 1), effective_to=None,
            published_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        stock = _make_stock(setup_session)
        _make_rising_price_history(setup_session, stock.id, last_session=friday)
        setup_session.commit()
    finally:
        setup_session.close()

    frozen = datetime(saturday.year, saturday.month, saturday.day, 12, 0, tzinfo=timezone.utc)
    _FrozenDateTime._frozen_now = frozen

    monkeypatch.setattr(run_discovery_scan_module, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(run_discovery_scan_module, "datetime", _FrozenDateTime)

    summary = run_discovery_scan_module.run([])

    # The bug: without the fix, scan_date defaults to Saturday (a
    # non-trading day) and this candidate is wrongly excluded as
    # stale_market_data (Friday's real, fresh candle < Saturday).
    assert summary["scan_date"] == friday.isoformat()
    assert summary["candidates_eligible"] == 1
    assert summary["candidates_excluded_by_reason"] == {}
    assert summary["status"] == "ok"
