"""EPIC-M1.62: automatically determine whether an active recommendation
remains valid after material market, news, event, or model changes,
producing an explicit `UNCHANGED`/`UPDATED`/`WITHDRAWN`/`EXPIRED` outcome.

Composes rather than duplicates: M1.36's `RecommendationObservation` (for
current price/return and elapsed time), M1.35's `check_market_data_
freshness` (for stale/missing data detection), and M1.47's
`RecommendationPublication` (for target/stop-loss proximity). Never writes
to `Prediction` or any of those tables -- "historical versions remain
immutable" (AC) holds structurally, and a caller who decides `UPDATED`
warrants an actual new version composes this with M1.55's
`create_recommendation_revision` separately, using a freshly-scored
`Prediction` this module never produces itself.

Checks run in a fixed priority order, any one of which determines the
outcome (scope: "detect material changes in recommendation inputs"):
1. **Horizon expiry** -- the recommendation's own horizon has elapsed with
   no closing outcome yet -> `EXPIRED`.
2. **Stop-loss proximity** -- the current return is within
   `PROXIMITY_THRESHOLD` of the stop -> `WITHDRAWN` (a recommendation this
   close to being stopped out should not be presented as still fully
   "active" -- AC: "material invalidation cannot leave a stale
   recommendation active").
3. **Stale/missing market data** -- M1.35's own freshness check fails ->
   `WITHDRAWN` (can no longer confirm continued validity).
4. **Model version changed** -- a newer `model_version` has been used
   platform-wide since this prediction was made -> `UPDATED` (a fresh look
   under the current model is warranted).
5. **Target proximity** -- the current return is within
   `PROXIMITY_THRESHOLD` of the target -> `UPDATED` (an early, strong
   move warrants revalidation).
6. Otherwise -> `UNCHANGED`.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Prediction, RecommendationRevalidationOutcome
from .recommendation_tracking import get_recommendation_tracking_history
from .refresh_policy import REASON_STALE_DATA, check_market_data_freshness
from .target_stop_loss import get_publication

REVALIDATION_ENGINE_VERSION = "RVE-001"

OUTCOME_UNCHANGED = "UNCHANGED"
OUTCOME_UPDATED = "UPDATED"
OUTCOME_WITHDRAWN = "WITHDRAWN"
OUTCOME_EXPIRED = "EXPIRED"

# A current return this close (90%) to the target or stop is a material
# change worth revalidating for, even before the level is technically
# crossed. Fixed, documented, versioned -- not learned or fitted.
PROXIMITY_THRESHOLD = Decimal("0.90")


def _current_state(session: Session, prediction: Prediction) -> tuple[int, Decimal | None]:
    history = get_recommendation_tracking_history(session, prediction.id)
    if not history:
        return 0, None
    latest = history[-1]
    return latest.day_number, latest.return_since_entry


def _latest_model_version(session: Session, as_of: datetime) -> str | None:
    return session.scalar(
        select(Prediction.model_version)
        .where(Prediction.as_of_timestamp <= as_of)
        .order_by(Prediction.as_of_timestamp.desc(), Prediction.id.desc())
    )


def revalidate_recommendation(
    session: Session, prediction: Prediction, *, checked_at: datetime
) -> RecommendationRevalidationOutcome:
    """Deterministic (AC) and idempotent by `(prediction_id, checked_at)`
    (AC) -- re-running the exact same check at the exact same point in time
    returns the original outcome unchanged rather than re-deriving it."""
    existing = session.scalar(
        select(RecommendationRevalidationOutcome).where(
            RecommendationRevalidationOutcome.prediction_id == prediction.id,
            RecommendationRevalidationOutcome.checked_at == checked_at,
        )
    )
    if existing is not None:
        return existing

    elapsed_days, current_return = _current_state(session, prediction)

    outcome = OUTCOME_UNCHANGED
    reason = "no material change detected"

    if elapsed_days >= prediction.horizon_days:
        outcome = OUTCOME_EXPIRED
        reason = f"horizon of {prediction.horizon_days} day(s) elapsed ({elapsed_days} observed) with no closing outcome"
    else:
        publication = get_publication(session, prediction.id)
        if publication is not None and publication.published and current_return is not None:
            if current_return <= -publication.downside_percentage * PROXIMITY_THRESHOLD:
                outcome = OUTCOME_WITHDRAWN
                reason = f"current return {current_return} is within {PROXIMITY_THRESHOLD:.0%} of the stop-loss level"

        if outcome == OUTCOME_UNCHANGED:
            freshness = check_market_data_freshness(session, prediction.stock_id, checked_at)
            if not freshness.is_fresh:
                outcome = OUTCOME_WITHDRAWN
                reason = f"underlying market data is {freshness.reason or REASON_STALE_DATA}; cannot confirm continued validity"

        if outcome == OUTCOME_UNCHANGED:
            latest_model_version = _latest_model_version(session, checked_at)
            if latest_model_version is not None and latest_model_version != prediction.model_version:
                outcome = OUTCOME_UPDATED
                reason = f"model version has changed from {prediction.model_version} to {latest_model_version} since this recommendation was made"

        if outcome == OUTCOME_UNCHANGED and publication is not None and publication.published and current_return is not None:
            if current_return >= publication.upside_percentage * PROXIMITY_THRESHOLD:
                outcome = OUTCOME_UPDATED
                reason = f"current return {current_return} is within {PROXIMITY_THRESHOLD:.0%} of the target level"

    record = RecommendationRevalidationOutcome(
        prediction_id=prediction.id,
        outcome=outcome,
        reason=reason,
        elapsed_days=elapsed_days,
        current_return=current_return,
        evidence_timestamp=checked_at,
        checked_at=checked_at,
        revalidation_engine_version=REVALIDATION_ENGINE_VERSION,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def get_revalidation_history(session: Session, prediction_id: int) -> tuple[RecommendationRevalidationOutcome, ...]:
    return tuple(
        session.scalars(
            select(RecommendationRevalidationOutcome)
            .where(RecommendationRevalidationOutcome.prediction_id == prediction_id)
            .order_by(RecommendationRevalidationOutcome.id.asc())
        ).all()
    )
