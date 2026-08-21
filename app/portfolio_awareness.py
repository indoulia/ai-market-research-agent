"""EPIC-M1.59: make recommendations aware of a user's existing holdings and
the platform's currently-active recommendations, without ever changing the
underlying opportunity score.

There is no brokerage integration in this repo, so a holding is only ever
what the user explicitly declares (`record_holding`) -- never inferred or
fabricated. Recommendations themselves are not user-scoped in this
platform (M1.46 only personalizes *visibility* of the same system-wide
picks); "active recommendation exposure" therefore means every currently
open (`Prediction.status == "OPEN"`), currently-selected (M1.14's
`RecommendationSelection.selected`) recommendation system-wide, combined
with one user's own declared holdings, to assess whether a *candidate*
stock would concentrate that user's combined exposure.

Purely additive and read-only for the assessment itself (only
`record_holding` writes anything, and only to its own new table) --
`Prediction.opportunity_score` and every other scoring field are never
read for the purpose of being changed, only `Stock.sector` is read (scope:
"keep recommendation quality separate from allocation decisions"; AC: "no
automatic trading or allocation is performed").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import (
    Prediction,
    RecommendationGeneration,
    RecommendationSelection,
    ScanCandidate,
    Stock,
    UserHolding,
)

ACTION_HELD = "HELD"
ACTION_SOLD = "SOLD"
VALID_ACTIONS = (ACTION_HELD, ACTION_SOLD)

# A fixed, documented, versioned concentration policy -- not learned or
# fitted. Adding one more position in a sector that would reach this many
# combined (holdings + active recommendations) positions is flagged.
SECTOR_CONCENTRATION_THRESHOLD = 3

REASON_ALREADY_HELD = "ALREADY_HELD"
REASON_ALREADY_ACTIVE_RECOMMENDATION = "ALREADY_ACTIVE_RECOMMENDATION"
REASON_SECTOR_CONCENTRATION = "SECTOR_CONCENTRATION"


class InvalidHoldingError(ValueError):
    pass


class UserHoldingImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = ("user_id", "stock_id", "action", "quantity", "recorded_at", "created_at")


@event.listens_for(UserHolding, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise UserHoldingImmutableError(f"user holding {target.id} field(s) {changed} cannot be modified after creation")


@dataclass(frozen=True)
class PortfolioConflictAssessment:
    user_id: str
    candidate_stock_id: int
    candidate_sector: str | None
    already_held: bool
    already_active_recommendation: bool
    sector_exposure_count: int
    sector_concentration_warning: bool
    conflicts: tuple[str, ...]


def record_holding(
    session: Session, *, user_id: str, stock_id: int, action: str, recorded_at: datetime, quantity: Decimal | None = None
) -> UserHolding:
    """Always inserts a new event -- current holdings are derived by
    reading the latest event per `(user_id, stock_id)`, never by mutating a
    prior one (AC: "portfolio exposure is computed deterministically")."""
    if action not in VALID_ACTIONS:
        raise InvalidHoldingError(f"action must be one of {VALID_ACTIONS}, got {action!r}")

    holding = UserHolding(
        user_id=user_id, stock_id=stock_id, action=action, quantity=quantity, recorded_at=recorded_at
    )
    session.add(holding)
    session.commit()
    session.refresh(holding)
    return holding


def get_current_holdings(session: Session, user_id: str) -> tuple[Stock, ...]:
    """The latest recorded action per stock for `user_id`, filtered to
    those currently `HELD` -- deterministic and reproducible from the
    immutable event log."""
    events = session.scalars(
        select(UserHolding).where(UserHolding.user_id == user_id).order_by(UserHolding.id.asc())
    ).all()
    latest_action_by_stock: dict[int, str] = {}
    for event_row in events:
        latest_action_by_stock[event_row.stock_id] = event_row.action

    held_stock_ids = [stock_id for stock_id, action in latest_action_by_stock.items() if action == ACTION_HELD]
    if not held_stock_ids:
        return ()
    return tuple(session.scalars(select(Stock).where(Stock.id.in_(held_stock_ids)).order_by(Stock.id.asc())).all())


def _active_recommendation_stocks(session: Session) -> tuple[Stock, ...]:
    """Every stock with a currently open, currently-selected recommendation,
    system-wide -- recommendations are not user-scoped in this platform."""
    rows = session.execute(
        select(Stock)
        .join(ScanCandidate, ScanCandidate.stock_id == Stock.id)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .join(RecommendationSelection, RecommendationSelection.recommendation_generation_id == RecommendationGeneration.id)
        .join(Prediction, Prediction.id == RecommendationGeneration.prediction_id)
        .where(RecommendationSelection.selected.is_(True), Prediction.status == "OPEN")
    ).scalars().all()
    return tuple(rows)


def assess_portfolio_conflict(session: Session, *, user_id: str, candidate_stock_id: int) -> PortfolioConflictAssessment:
    """Deterministic and reproducible (AC): a pure read-side computation
    over the user's current holdings and the platform's current active
    recommendation exposure. Never touches `Prediction.opportunity_score`
    or any other scoring field -- recommendations remain individually
    auditable regardless of this assessment's outcome (AC)."""
    candidate = session.get(Stock, candidate_stock_id)
    holdings = get_current_holdings(session, user_id)
    active = _active_recommendation_stocks(session)

    exposure_by_stock_id: dict[int, Stock] = {s.id: s for s in holdings}
    for stock in active:
        exposure_by_stock_id.setdefault(stock.id, stock)

    already_held = candidate_stock_id in {s.id for s in holdings}
    already_active = candidate_stock_id in {s.id for s in active} and not already_held

    sector = candidate.sector if candidate is not None else None
    sector_exposure_count = sum(
        1 for stock_id, stock in exposure_by_stock_id.items() if stock_id != candidate_stock_id and stock.sector == sector
    ) if sector is not None else 0

    concentration_warning = sector is not None and (sector_exposure_count + 1) >= SECTOR_CONCENTRATION_THRESHOLD

    conflicts = []
    if already_held:
        conflicts.append(REASON_ALREADY_HELD)
    if already_active:
        conflicts.append(REASON_ALREADY_ACTIVE_RECOMMENDATION)
    if concentration_warning:
        conflicts.append(
            f"{REASON_SECTOR_CONCENTRATION}:{sector} (would bring combined exposure to {sector_exposure_count + 1})"
        )

    return PortfolioConflictAssessment(
        user_id=user_id,
        candidate_stock_id=candidate_stock_id,
        candidate_sector=sector,
        already_held=already_held,
        already_active_recommendation=already_active,
        sector_exposure_count=sector_exposure_count,
        sector_concentration_warning=concentration_warning,
        conflicts=tuple(conflicts),
    )
