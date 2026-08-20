from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Stock, WatchlistEntry
from app.watchlist_intake import (
    ACTION_ACTIVATE,
    ACTION_DEACTIVATE,
    SOURCE_USER,
    InvalidSymbolError,
    UnsupportedSymbolError,
    WatchlistEntryImmutableError,
    add_to_watchlist,
    get_active_watchlist,
    get_watchlist_history,
    is_active,
    remove_from_watchlist,
)

AS_OF = datetime(2026, 8, 21, tzinfo=timezone.utc)


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


def _make_stock(session, symbol="RELIANCE", is_active_flag=True):
    stock = Stock(symbol=symbol, exchange="NSE", is_active=is_active_flag)
    session.add(stock)
    session.flush()
    return stock


def test_valid_symbol_is_added_with_provenance(session):
    stock = _make_stock(session)

    entry = add_to_watchlist(session, symbol="RELIANCE", requested_at=AS_OF)

    assert entry.stock_id == stock.id
    assert entry.symbol == "RELIANCE"
    assert entry.source == SOURCE_USER
    assert entry.action == ACTION_ACTIVATE
    # sqlite drops tzinfo on DateTime(timezone=True) round-trips; compare naively.
    assert entry.requested_at.replace(tzinfo=None) == AS_OF.replace(tzinfo=None)
    assert is_active(session, stock.id) is True


def test_invalid_blank_symbol_is_rejected_before_any_lookup(session):
    with pytest.raises(InvalidSymbolError):
        add_to_watchlist(session, symbol="   ", requested_at=AS_OF)
    assert session.query(WatchlistEntry).count() == 0


def test_unknown_symbol_is_rejected_explicitly(session):
    with pytest.raises(UnsupportedSymbolError, match="unknown symbol"):
        add_to_watchlist(session, symbol="NOSUCHSTOCK", requested_at=AS_OF)
    assert session.query(WatchlistEntry).count() == 0


def test_inactive_symbol_is_rejected_explicitly(session):
    _make_stock(session, "DELISTED", is_active_flag=False)

    with pytest.raises(UnsupportedSymbolError, match="inactive symbol"):
        add_to_watchlist(session, symbol="DELISTED", requested_at=AS_OF)
    assert session.query(WatchlistEntry).count() == 0


def test_duplicate_intake_is_idempotent(session):
    stock = _make_stock(session)

    first = add_to_watchlist(session, symbol="RELIANCE", requested_at=AS_OF)
    second = add_to_watchlist(session, symbol="RELIANCE", requested_at=AS_OF)

    assert first.id == second.id
    assert session.query(WatchlistEntry).filter_by(stock_id=stock.id).count() == 1


def test_remove_then_readd_preserves_full_history(session):
    stock = _make_stock(session)

    add_to_watchlist(session, symbol="RELIANCE", requested_at=AS_OF)
    remove_from_watchlist(session, symbol="RELIANCE", requested_at=AS_OF)
    assert is_active(session, stock.id) is False
    add_to_watchlist(session, symbol="RELIANCE", requested_at=AS_OF)
    assert is_active(session, stock.id) is True

    history = get_watchlist_history(session, stock.id)
    assert [h.action for h in history] == [ACTION_ACTIVATE, ACTION_DEACTIVATE, ACTION_ACTIVATE]


def test_removing_a_never_added_symbol_still_records_an_explicit_event(session):
    stock = _make_stock(session)

    entry = remove_from_watchlist(session, symbol="RELIANCE", requested_at=AS_OF)

    assert entry.action == ACTION_DEACTIVATE
    assert is_active(session, stock.id) is False


def test_get_active_watchlist_lists_only_currently_active_stocks(session):
    active_stock = _make_stock(session, "ACTIVE1")
    removed_stock = _make_stock(session, "REMOVED1")
    add_to_watchlist(session, symbol="ACTIVE1", requested_at=AS_OF)
    add_to_watchlist(session, symbol="REMOVED1", requested_at=AS_OF)
    remove_from_watchlist(session, symbol="REMOVED1", requested_at=AS_OF)

    active = get_active_watchlist(session)

    assert [s.symbol for s in active] == ["ACTIVE1"]


def test_watchlist_entry_is_immutable_after_creation(session):
    _make_stock(session)
    entry = add_to_watchlist(session, symbol="RELIANCE", requested_at=AS_OF)

    entry.action = ACTION_DEACTIVATE
    with pytest.raises(WatchlistEntryImmutableError, match="action"):
        session.flush()
    session.rollback()
