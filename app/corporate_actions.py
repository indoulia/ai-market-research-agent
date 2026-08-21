"""EPIC-M1.96: ensure historical prices, securities, identities and
outcomes remain economically correct across corporate actions and
security lifecycle changes.

`CorporateAction` is a new, additive, append-only table -- recording an
action never mutates an existing `MarketPrice` row (scope: "preserve raw
and adjusted representations with provenance"). Raw prices as originally
ingested (M1.3) remain untouched forever; an *adjusted* view is always a
pure, derived computation (`compute_price_adjustment_factor`) applied at
read time, never a destructive rewrite of history.

Split/bonus/rights actions are handled with an exact, unambiguous `ratio`
(new shares per old share) -- multiplying a later raw price by the
cumulative ratio of every such action between two dates brings it back to
an earlier date's economic basis, which is exactly what `app.outcomes.
evaluate_recommendation` needs to compare a post-split raw price against
a pre-split `entry_price` without a fabricated "loss". Cash dividends are
recorded for provenance (scope: "handle ... dividends") but deliberately
NOT applied as a price adjustment here -- doing so correctly requires
estimating the pre-ex-date closing price, which is a real, separate
estimation problem this EPIC does not fabricate an answer to; a dividend
record is honestly available for a future EPIC to build that on.

Symbol changes update `Stock.symbol` in place (the security's identity
persists under a new name) while the immutable `CorporateAction` row
preserves the full old-symbol/new-symbol history permanently (AC:
"security identity changes are traceable"). Delistings flip `Stock.
is_active` through this same traced, versioned path instead of an
untracked direct mutation -- no code in this platform ever deletes a
`Stock` row, and no historical report in this platform filters by
`is_active` (verified: only `app.market_data.ingest`, `app.scan`, and the
personal watchlist modules do, all correctly live-only concerns) -- so a
delisted security's historical `Prediction`/`PredictionOutcome` rows are
never silently excluded from historical datasets (AC).

Mergers and demergers are recordable for provenance but this EPIC does
not attempt automatic price-series stitching across two different
`Stock` rows -- that requires a real predecessor/successor security
mapping this codebase has no data model for today, and fabricating one
would risk silently misrepresenting history rather than honestly leaving
it unhandled.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import CorporateAction, Stock

CORPORATE_ACTION_VERSION = "CPA-001"

ACTION_SPLIT = "SPLIT"
ACTION_BONUS = "BONUS"
ACTION_RIGHTS = "RIGHTS"
ACTION_DIVIDEND = "DIVIDEND"
ACTION_SYMBOL_CHANGE = "SYMBOL_CHANGE"
ACTION_MERGER = "MERGER"
ACTION_DEMERGER = "DEMERGER"
ACTION_DELISTING = "DELISTING"

ALL_ACTION_TYPES = (
    ACTION_SPLIT, ACTION_BONUS, ACTION_RIGHTS, ACTION_DIVIDEND,
    ACTION_SYMBOL_CHANGE, ACTION_MERGER, ACTION_DEMERGER, ACTION_DELISTING,
)

# These action types carry an exact, unambiguous share-count ratio and are
# the only ones `compute_price_adjustment_factor` uses (see module docstring
# for why dividends are recorded but not price-adjusted here).
RATIO_ACTION_TYPES = (ACTION_SPLIT, ACTION_BONUS, ACTION_RIGHTS)

IMMUTABLE_FIELDS = (
    "stock_id",
    "action_type",
    "effective_date",
    "ratio",
    "cash_amount",
    "old_symbol",
    "new_symbol",
    "source",
    "action_version",
    "recorded_at",
    "created_at",
)


class CorporateActionImmutableError(RuntimeError):
    pass


class InvalidCorporateActionError(ValueError):
    pass


@event.listens_for(CorporateAction, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise CorporateActionImmutableError(
            f"corporate action {target.id} field(s) {changed} cannot be modified after creation"
        )


def record_corporate_action(
    session: Session,
    *,
    stock: Stock,
    action_type: str,
    effective_date: date,
    source: str,
    recorded_at: datetime,
    ratio: Decimal | None = None,
    cash_amount: Decimal | None = None,
    new_symbol: str | None = None,
) -> CorporateAction:
    """Records one corporate action as immutable historical fact, applying
    the one real, traced side effect each action type requires (a symbol
    rename, or flipping `is_active` on delisting) -- never a silent,
    untracked mutation of `Stock` elsewhere."""
    if action_type not in ALL_ACTION_TYPES:
        raise InvalidCorporateActionError(f"action_type must be one of {ALL_ACTION_TYPES}, got {action_type!r}")

    if action_type in RATIO_ACTION_TYPES:
        if ratio is None or ratio <= 0:
            raise InvalidCorporateActionError(f"{action_type} requires a positive ratio")
    if action_type == ACTION_DIVIDEND:
        if cash_amount is None or cash_amount <= 0:
            raise InvalidCorporateActionError(f"{action_type} requires a positive cash_amount")
    if action_type == ACTION_SYMBOL_CHANGE and not new_symbol:
        raise InvalidCorporateActionError(f"{action_type} requires new_symbol")

    old_symbol = stock.symbol if action_type == ACTION_SYMBOL_CHANGE else None

    action = CorporateAction(
        stock_id=stock.id,
        action_type=action_type,
        effective_date=effective_date,
        ratio=ratio,
        cash_amount=cash_amount,
        old_symbol=old_symbol,
        new_symbol=new_symbol if action_type == ACTION_SYMBOL_CHANGE else None,
        source=source,
        action_version=CORPORATE_ACTION_VERSION,
        recorded_at=recorded_at,
    )
    session.add(action)

    if action_type == ACTION_SYMBOL_CHANGE:
        stock.symbol = new_symbol
    elif action_type == ACTION_DELISTING:
        stock.is_active = False

    session.commit()
    session.refresh(action)
    return action


def get_corporate_actions(
    session: Session, stock_id: int, *, start: date | None = None, end: date | None = None
) -> tuple[CorporateAction, ...]:
    query = select(CorporateAction).where(CorporateAction.stock_id == stock_id)
    if start is not None:
        query = query.where(CorporateAction.effective_date >= start)
    if end is not None:
        query = query.where(CorporateAction.effective_date <= end)
    return tuple(session.scalars(query.order_by(CorporateAction.effective_date.asc())).all())


def compute_price_adjustment_factor(
    session: Session, stock_id: int, *, reference_date: date, price_date: date
) -> Decimal:
    """The factor that brings a raw price recorded on `price_date` onto
    `reference_date`'s economic basis: the cumulative product of every
    ratio-bearing action's `ratio` with `reference_date < effective_date
    <= price_date`. A split/bonus/rights action exactly on
    `reference_date` is excluded (it already defines that date's basis);
    one exactly on `price_date` is included (it has already taken effect
    by the time that price was recorded). Returns `Decimal("1")` -- a
    true no-op -- when `price_date <= reference_date` or no qualifying
    action exists, so a stock with no recorded corporate actions is
    always adjusted by exactly 1 (AC: "historical returns remain correct
    across corporate actions" holds trivially, and with zero regression
    risk, when there are none to correct for)."""
    if price_date <= reference_date:
        return Decimal("1")

    actions = session.scalars(
        select(CorporateAction).where(
            CorporateAction.stock_id == stock_id,
            CorporateAction.action_type.in_(RATIO_ACTION_TYPES),
            CorporateAction.effective_date > reference_date,
            CorporateAction.effective_date <= price_date,
        )
    ).all()

    factor = Decimal("1")
    for action in actions:
        factor *= action.ratio
    return factor


def adjust_price(raw_price: Decimal, factor: Decimal) -> Decimal:
    return raw_price * factor
