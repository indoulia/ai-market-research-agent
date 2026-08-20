"""EPIC-M1.36: track every issued recommendation from issuance through its
selected horizon using immutable daily observations -- one row per trading
day, recorded once and never overwritten. This is genuinely new relative to
M1.5/M1.15/M1.21's outcome-closure mechanism: those compute a single final
outcome for the whole horizon window at once; this module additionally
captures the day-by-day price/return trajectory *during* that window, so a
recommendation's progress can be reconstructed at any point, not only its
terminal result.

"Preserve original score, probability, horizon, model, and data snapshot"
(scope) requires no new code here: `Prediction` is already immutable (M1.13's
own guard); this module only ever reads it, never writes to it.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import MarketPrice, Prediction, RecommendationObservation

OBSERVATION_RULE_VERSION = "RTK-001"


class RecommendationObservationImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "observation_date",
    "day_number",
    "close_price",
    "return_since_entry",
    "data_available",
    "horizon_complete",
    "observation_rule_version",
    "created_at",
)


@event.listens_for(RecommendationObservation, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise RecommendationObservationImmutableError(
            f"recommendation observation {target.id} field(s) {changed} cannot be modified after creation"
        )


def _has_valid_ohlc(row: MarketPrice) -> bool:
    prices = (row.open, row.high, row.low, row.close)
    if any(price <= 0 for price in prices):
        return False
    if row.volume <= 0:
        return False
    if row.high < max(row.open, row.low, row.close):
        return False
    if row.low > min(row.open, row.high, row.close):
        return False
    return True


def record_daily_observations(session: Session, prediction: Prediction) -> tuple[RecommendationObservation, ...]:
    """Record one observation per trading day since `prediction.as_of_timestamp`,
    up to `prediction.horizon_days`. Idempotent and resumable: a day already
    observed (`(prediction_id, day_number)` uniqueness) is never revisited,
    and a day whose market data hasn't arrived yet simply isn't created until
    a later call finds it -- exactly the pattern M1.15's scheduler already
    uses for the single final outcome, applied here per day. Missing market
    data for a day that HAS arrived (invalid OHLC) is recorded explicitly as
    `data_available=False` with no fabricated price/return, never silently
    skipped or guessed at."""
    existing_days = set(
        session.scalars(
            select(RecommendationObservation.day_number).where(
                RecommendationObservation.prediction_id == prediction.id
            )
        ).all()
    )

    rows = session.scalars(
        select(MarketPrice)
        .where(MarketPrice.stock_id == prediction.stock_id, MarketPrice.timestamp > prediction.as_of_timestamp)
        .order_by(MarketPrice.timestamp.asc())
    ).all()

    created = []
    for day_number, row in enumerate(rows, start=1):
        if day_number > prediction.horizon_days:
            break
        if day_number in existing_days:
            continue

        valid = _has_valid_ohlc(row)
        close_price = row.close if valid else None
        return_since_entry = (row.close - prediction.entry_price) / prediction.entry_price if valid else None

        observation = RecommendationObservation(
            prediction_id=prediction.id,
            observation_date=row.timestamp,
            day_number=day_number,
            close_price=close_price,
            return_since_entry=return_since_entry,
            data_available=valid,
            horizon_complete=(day_number == prediction.horizon_days),
            observation_rule_version=OBSERVATION_RULE_VERSION,
        )
        session.add(observation)
        created.append(observation)

    if created:
        session.commit()
        for observation in created:
            session.refresh(observation)
    return tuple(created)


def get_recommendation_tracking_history(session: Session, prediction_id: int) -> tuple[RecommendationObservation, ...]:
    """Full, immutable, day-ordered observation history -- reconstructs a
    recommendation's tracked progress at any point (AC: "historical tracking
    can be reconstructed for any recommendation")."""
    return tuple(
        session.scalars(
            select(RecommendationObservation)
            .where(RecommendationObservation.prediction_id == prediction_id)
            .order_by(RecommendationObservation.day_number.asc())
        ).all()
    )
