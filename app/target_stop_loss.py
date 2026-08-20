"""EPIC-M1.47: produce an explicit, internally consistent target price,
stop-loss price, upside/downside percentage, and reward/risk ratio for every
published recommendation -- freezing those values under a versioned
methodology rather than leaving `Prediction.target_return`/`stop_return`
(M1.4/M1.13's own percentage-only fields) as the only representation.

Deliberately does not modify `app/recommendations.py` (M1.4): `Prediction`
already carries `entry_price`/`target_return`/`stop_return`/`horizon_days`,
all immutable since creation. This module only *derives* absolute prices and
validated percentages from those existing, frozen fields -- it never
recomputes or overrides them.

Reward/risk and price derivation are pure arithmetic from
`entry_price * (1 + return)`, so the derived percentage always reconciles
exactly with the derived price by construction (AC: "derived percentages
reconcile exactly with stored prices") -- verified directly by an assertion
in `publish_recommendation`, not merely assumed.

"Freeze published values; later changes become a new recommendation
version" (scope) is implemented the same way M1.39's dataset versioning
works: one immutable row per `(prediction_id, methodology_version)`. A
different `TARGET_STOP_METHODOLOGY_VERSION` in the future produces an
entirely separate row, never a mutation of a previously published one.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import Prediction, RecommendationPublication

TARGET_STOP_METHODOLOGY_VERSION = "TSL-001"

REASON_NON_POSITIVE_ENTRY_PRICE = "NON_POSITIVE_ENTRY_PRICE"
REASON_TARGET_NOT_ABOVE_ENTRY = "TARGET_NOT_ABOVE_ENTRY"
REASON_STOP_NOT_BELOW_ENTRY = "STOP_NOT_BELOW_ENTRY"


class RecommendationPublicationImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "methodology_version",
    "entry_price",
    "target_price",
    "stop_loss_price",
    "horizon_days",
    "upside_percentage",
    "downside_percentage",
    "reward_risk_ratio",
    "published",
    "rejection_reason",
    "published_at",
    "created_at",
)


@event.listens_for(RecommendationPublication, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise RecommendationPublicationImmutableError(
            f"recommendation publication {target.id} field(s) {changed} cannot be modified after creation"
        )


def _rejection_reason(entry_price: Decimal, target_return: Decimal, stop_return: Decimal) -> str | None:
    if entry_price <= 0:
        return REASON_NON_POSITIVE_ENTRY_PRICE
    if target_return <= 0:
        return REASON_TARGET_NOT_ABOVE_ENTRY
    if stop_return >= 0:
        return REASON_STOP_NOT_BELOW_ENTRY
    return None


def publish_recommendation(
    session: Session,
    prediction: Prediction,
    *,
    published_at: datetime,
    methodology_version: str = TARGET_STOP_METHODOLOGY_VERSION,
) -> RecommendationPublication:
    """Deterministic for the same `prediction` and `methodology_version`
    (AC): idempotent by `(prediction_id, methodology_version)` uniqueness --
    an already-published (or already-rejected) attempt under this exact
    methodology version returns its original row unchanged, never
    re-derived (AC: "historical recommendations retain their original
    values"). An invalid or contradictory input is still recorded, with
    `published=False` and an explicit `rejection_reason`, rather than
    silently producing nothing (AC: "invalid or contradictory values
    prevent publication")."""
    existing = session.scalar(
        select(RecommendationPublication).where(
            RecommendationPublication.prediction_id == prediction.id,
            RecommendationPublication.methodology_version == methodology_version,
        )
    )
    if existing is not None:
        return existing

    entry_price = prediction.entry_price
    target_return = prediction.target_return
    stop_return = prediction.stop_return

    target_price = entry_price * (Decimal("1") + target_return)
    stop_loss_price = entry_price * (Decimal("1") + stop_return)
    upside_percentage = target_return
    downside_percentage = -stop_return

    rejection_reason = _rejection_reason(entry_price, target_return, stop_return)

    if rejection_reason is None:
        # Derived by construction from the same inputs -- must always
        # reconcile exactly; if this ever fails, it is a bug in this
        # function, not a legitimate rejection case. Only checked once
        # `entry_price` is known to be positive (a non-positive entry price
        # is itself a rejection, not a reconciliation failure).
        assert (target_price - entry_price) / entry_price == upside_percentage
        assert (stop_loss_price - entry_price) / entry_price == stop_return

    reward_risk_ratio = (upside_percentage / downside_percentage) if downside_percentage != 0 else None

    publication = RecommendationPublication(
        prediction_id=prediction.id,
        methodology_version=methodology_version,
        entry_price=entry_price,
        target_price=target_price,
        stop_loss_price=stop_loss_price,
        horizon_days=prediction.horizon_days,
        upside_percentage=upside_percentage,
        downside_percentage=downside_percentage,
        reward_risk_ratio=reward_risk_ratio,
        published=(rejection_reason is None),
        rejection_reason=rejection_reason,
        published_at=published_at,
    )
    session.add(publication)
    session.commit()
    session.refresh(publication)
    return publication


def get_publication(
    session: Session, prediction_id: int, *, methodology_version: str = TARGET_STOP_METHODOLOGY_VERSION
) -> RecommendationPublication | None:
    return session.scalar(
        select(RecommendationPublication).where(
            RecommendationPublication.prediction_id == prediction_id,
            RecommendationPublication.methodology_version == methodology_version,
        )
    )
