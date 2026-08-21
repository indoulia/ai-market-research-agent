"""EPIC-M1.61: represent short-, medium-, and long-term views of one stock
independently, and deterministically resolve which one to present when more
than one is currently open at once -- never hiding a material conflicting
view.

This platform's horizon selection (M1.10) only ever produces short-term
(1-7 day) predictions today; "multi-horizon" in practice means comparing
several currently-open predictions for the same stock that happened to be
made at different times with different M1.10-selected horizons (1, 3, 5, or
7 days), each carrying its own already-immutable score/confidence
(`Prediction`) and target/SL (M1.47's `RecommendationPublication`) -- this
module never recomputes any of those, only compares and picks among them.

Presentation priority is driven by M1.46's own `UserPreference.horizon_band`
(scope: "define deterministic presentation priority based on user
preference"); a resolution is a new, immutable row every time -- re-resolving
as new predictions arrive never edits a prior decision, only supersedes it
(AC: "historical horizon decisions remain immutable").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import MultiHorizonResolution, Prediction
from .user_preferences import HORIZON_BAND_CUSTOM, HORIZON_BAND_DAY_RANGES, get_current_preference

MULTI_HORIZON_RESOLUTION_VERSION = "MHR-001"

# A score spread this large between the best and any other currently-open
# horizon view for the same stock is a material disagreement worth
# surfacing, not noise. Fixed, documented, versioned -- not learned.
CONFLICT_SCORE_MARGIN = Decimal("20.00")


class NoOpenRecommendationError(RuntimeError):
    pass


@dataclass(frozen=True)
class HorizonView:
    prediction_id: int
    horizon_days: int
    opportunity_score: Decimal
    confidence: Decimal
    as_of_timestamp: datetime


def _open_predictions(session: Session, stock_id: int) -> tuple[Prediction, ...]:
    return tuple(
        session.scalars(
            select(Prediction)
            .where(Prediction.stock_id == stock_id, Prediction.status == "OPEN")
            .order_by(Prediction.as_of_timestamp.asc())
        ).all()
    )


def _matches_preferred_band(preference, horizon_days: int) -> bool:
    if preference.horizon_band == HORIZON_BAND_CUSTOM:
        return horizon_days == preference.custom_horizon_days
    lower, upper = HORIZON_BAND_DAY_RANGES[preference.horizon_band]
    if horizon_days < lower:
        return False
    return upper is None or horizon_days <= upper


def get_horizon_views(session: Session, stock_id: int) -> tuple[HorizonView, ...]:
    """Every currently-open prediction for `stock_id`, each with its own
    preserved score/confidence/horizon (scope: "preserve horizon-specific
    scores, confidence, target, and SL" -- target/SL remain queryable via
    M1.47 per `prediction_id`, not duplicated here)."""
    return tuple(
        HorizonView(
            prediction_id=p.id, horizon_days=p.horizon_days, opportunity_score=p.opportunity_score,
            confidence=p.confidence, as_of_timestamp=p.as_of_timestamp,
        )
        for p in _open_predictions(session, stock_id)
    )


def resolve_multi_horizon_view(
    session: Session, *, user_id: str, stock_id: int, resolved_at: datetime
) -> MultiHorizonResolution:
    """Picks a single primary view to present, deterministically, and
    surfaces every other currently-open view as a `conflicting` one when a
    material score disagreement exists -- never silently dropped (AC:
    "conflicts are explicitly surfaced"). Always inserts a new, immutable
    row (AC: "historical horizon decisions remain immutable")."""
    predictions = _open_predictions(session, stock_id)
    if not predictions:
        raise NoOpenRecommendationError(f"stock {stock_id} has no currently open recommendation to resolve")

    preference = get_current_preference(session, user_id, effective_at=resolved_at)
    matching = [p for p in predictions if _matches_preferred_band(preference, p.horizon_days)]
    candidates = matching if matching else predictions

    primary = max(candidates, key=lambda p: (p.opportunity_score, -p.id))
    others = [p for p in predictions if p.id != primary.id]

    conflicting_ids = [
        p.id for p in others if abs(p.opportunity_score - primary.opportunity_score) >= CONFLICT_SCORE_MARGIN
    ]
    has_conflict = bool(conflicting_ids)

    resolution = MultiHorizonResolution(
        user_id=user_id,
        stock_id=stock_id,
        primary_prediction_id=primary.id,
        primary_horizon_days=primary.horizon_days,
        conflicting_prediction_ids=conflicting_ids,
        has_conflict=has_conflict,
        resolved_at=resolved_at,
        resolution_rule_version=MULTI_HORIZON_RESOLUTION_VERSION,
    )
    session.add(resolution)
    session.commit()
    session.refresh(resolution)
    return resolution


def get_resolution_history(session: Session, *, user_id: str, stock_id: int) -> tuple[MultiHorizonResolution, ...]:
    return tuple(
        session.scalars(
            select(MultiHorizonResolution)
            .where(MultiHorizonResolution.user_id == user_id, MultiHorizonResolution.stock_id == stock_id)
            .order_by(MultiHorizonResolution.id.asc())
        ).all()
    )
