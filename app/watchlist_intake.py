"""EPIC-M1.18: a deterministic, persistent intake boundary for stocks a user (or
other discovery source) wants the recommendation system to monitor. This is the
*intake* step -- "should this stock be watched at all" -- distinct from and prior
to app/watchlist.py's (M1.7) *evaluation* step, which decides whether an already
-active watchlist stock currently qualifies as a positive opportunity. Nothing
here generates a recommendation or changes positive-consensus rules; it only
records intake events.

Watchlist membership is an append-only event log (ACTIVATE/DEACTIVATE), never a
mutable boolean column, so "preserve watchlist history rather than silently
overwriting prior intake events" holds by construction: the current active/
inactive state for a stock is always derived from its most recent event, and
every prior event remains exactly as it was recorded.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import Stock, WatchlistEntry

SOURCE_USER = "USER"

ACTION_ACTIVATE = "ACTIVATE"
ACTION_DEACTIVATE = "DEACTIVATE"


class InvalidSymbolError(ValueError):
    """Raised for a malformed symbol (empty/blank) -- a pure input-validation
    failure that never reaches the database."""


class UnsupportedSymbolError(RuntimeError):
    """Raised when a well-formed symbol is not part of the supported universe:
    either unknown (no matching `Stock` row) or known but currently inactive."""


class WatchlistEntryImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = ("stock_id", "symbol", "source", "action", "requested_at", "created_at")


@event.listens_for(WatchlistEntry, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise WatchlistEntryImmutableError(
            f"watchlist entry {target.id} field(s) {changed} cannot be modified after creation"
        )


def _validate_symbol_format(symbol: str) -> str:
    if symbol is None or not symbol.strip():
        raise InvalidSymbolError("symbol must be a non-empty string")
    return symbol.strip().upper()


def _resolve_supported_stock(session: Session, symbol: str) -> Stock:
    normalized = _validate_symbol_format(symbol)
    stock = session.scalar(select(Stock).where(Stock.symbol == normalized))
    if stock is None:
        raise UnsupportedSymbolError(f"unknown symbol: {normalized} is not part of the supported universe")
    if not stock.is_active:
        raise UnsupportedSymbolError(f"inactive symbol: {normalized} is not currently part of the active universe")
    return stock


def get_latest_entry(session: Session, stock_id: int) -> WatchlistEntry | None:
    return session.scalar(
        select(WatchlistEntry).where(WatchlistEntry.stock_id == stock_id).order_by(WatchlistEntry.id.desc())
    )


def is_active(session: Session, stock_id: int) -> bool:
    """Deterministic active/inactive state: derived solely from the most recent
    event for this stock, never from a separately mutated flag."""
    latest = get_latest_entry(session, stock_id)
    return latest is not None and latest.action == ACTION_ACTIVATE


def add_to_watchlist(
    session: Session, *, symbol: str, source: str = SOURCE_USER, requested_at: datetime
) -> WatchlistEntry:
    """Idempotent: if the stock is already active on the watchlist, returns the
    existing latest entry unchanged rather than inserting a redundant duplicate.
    Raises `InvalidSymbolError`/`UnsupportedSymbolError` for a malformed, unknown,
    or inactive symbol -- never silently ignored."""
    stock = _resolve_supported_stock(session, symbol)
    latest = get_latest_entry(session, stock.id)
    if latest is not None and latest.action == ACTION_ACTIVATE:
        return latest

    entry = WatchlistEntry(
        stock_id=stock.id,
        symbol=stock.symbol,
        source=source,
        action=ACTION_ACTIVATE,
        requested_at=requested_at,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def remove_from_watchlist(
    session: Session, *, symbol: str, source: str = SOURCE_USER, requested_at: datetime
) -> WatchlistEntry:
    """Idempotent: if the stock is already inactive (or was never added), a
    removal request for an already-inactive stock returns the existing latest
    entry rather than inserting a redundant duplicate. A stock with no prior
    entry at all gets its first (DEACTIVATE) event recorded, since an explicit
    "not watched" request is itself worth an auditable record."""
    stock = _resolve_supported_stock(session, symbol)
    latest = get_latest_entry(session, stock.id)
    if latest is not None and latest.action == ACTION_DEACTIVATE:
        return latest

    entry = WatchlistEntry(
        stock_id=stock.id,
        symbol=stock.symbol,
        source=source,
        action=ACTION_DEACTIVATE,
        requested_at=requested_at,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def get_watchlist_history(session: Session, stock_id: int) -> tuple[WatchlistEntry, ...]:
    """Full, immutable, chronologically ordered intake history for one stock."""
    return tuple(
        session.scalars(
            select(WatchlistEntry).where(WatchlistEntry.stock_id == stock_id).order_by(WatchlistEntry.id.asc())
        ).all()
    )


def get_active_watchlist(session: Session) -> tuple[Stock, ...]:
    """Every stock whose most recent watchlist event is ACTIVATE, deterministically."""
    all_stock_ids = session.scalars(select(WatchlistEntry.stock_id).distinct()).all()
    active_ids = [stock_id for stock_id in all_stock_ids if is_active(session, stock_id)]
    if not active_ids:
        return ()
    return tuple(session.scalars(select(Stock).where(Stock.id.in_(active_ids)).order_by(Stock.symbol)).all())
