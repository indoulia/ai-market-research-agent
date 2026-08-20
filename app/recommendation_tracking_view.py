"""EPIC-M1.51: give users a clear longitudinal view of every active and
completed recommendation from publication through outcome, by composing
M1.36's daily observations, M1.47's target/stop-loss publication, and M1.48's
evidence snapshot with the underlying `Prediction`/`PredictionOutcome` --
without introducing any new persisted state at all.

Purely read-only: this module writes nothing anywhere, so "tracking updates
do not rewrite the original recommendation snapshot" (AC) holds trivially --
there is no write path to violate it. `Prediction` is already immutable
(M1.4/M1.13's own guard); `RecommendationPublication` (M1.47),
`RecommendationEvidenceItem` (M1.48), and `RecommendationObservation` (M1.36)
are each already immutable in their own modules. This EPIC's only new
contribution is assembling them into one coherent view.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .evidence_snapshot import get_evidence_snapshot
from .models import (
    Prediction,
    PredictionOutcome,
    RecommendationEvidenceItem,
    RecommendationObservation,
    RecommendationPublication,
    Stock,
)
from .recommendation_tracking import get_recommendation_tracking_history
from .target_stop_loss import TARGET_STOP_METHODOLOGY_VERSION, get_publication

OUTCOME_STATUS_OPEN = "OPEN"


@dataclass(frozen=True)
class RecommendationTrackingView:
    prediction_id: int
    symbol: str
    as_of_timestamp: datetime
    entry_price: Decimal
    horizon_days: int
    elapsed_days: int
    confidence_at_publication: Decimal
    opportunity_score_at_publication: Decimal
    predicted_probability_at_publication: Decimal
    publication: RecommendationPublication | None
    current_price: Decimal | None
    current_return: Decimal | None
    target_progress: Decimal | None
    stop_progress: Decimal | None
    outcome_status: str
    outcome: PredictionOutcome | None
    evidence_snapshot: tuple[RecommendationEvidenceItem, ...]
    observation_history: tuple[RecommendationObservation, ...]


def _progress(current_return: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if current_return is None or denominator is None or denominator == 0:
        return None
    return current_return / denominator


def build_recommendation_tracking_view(
    session: Session, prediction: Prediction, *, methodology_version: str = TARGET_STOP_METHODOLOGY_VERSION
) -> RecommendationTrackingView:
    """Assembles the complete view for one recommendation. Original values
    (`entry_price`, `confidence_at_publication`, etc.) are read directly from
    the immutable `Prediction` row and displayed alongside current state
    (AC: "original recommendation values are visible beside current
    state")."""
    stock = session.get(Stock, prediction.stock_id)
    publication = get_publication(session, prediction.id, methodology_version=methodology_version)
    observation_history = get_recommendation_tracking_history(session, prediction.id)
    evidence = get_evidence_snapshot(session, prediction.id)
    outcome = session.scalar(select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction.id))

    latest_observation = observation_history[-1] if observation_history else None
    current_price = latest_observation.close_price if latest_observation else None
    current_return = latest_observation.return_since_entry if latest_observation else None
    elapsed_days = latest_observation.day_number if latest_observation else 0

    target_progress = _progress(current_return, publication.upside_percentage if publication else None)
    stop_progress = _progress(
        -current_return if current_return is not None else None,
        publication.downside_percentage if publication else None,
    )

    return RecommendationTrackingView(
        prediction_id=prediction.id,
        symbol=stock.symbol if stock else "",
        as_of_timestamp=prediction.as_of_timestamp,
        entry_price=prediction.entry_price,
        horizon_days=prediction.horizon_days,
        elapsed_days=elapsed_days,
        confidence_at_publication=prediction.confidence,
        opportunity_score_at_publication=prediction.opportunity_score,
        predicted_probability_at_publication=prediction.predicted_probability,
        publication=publication,
        current_price=current_price,
        current_return=current_return,
        target_progress=target_progress,
        stop_progress=stop_progress,
        outcome_status=outcome.outcome if outcome is not None else OUTCOME_STATUS_OPEN,
        outcome=outcome,
        evidence_snapshot=evidence,
        observation_history=observation_history,
    )


def get_recommendation_tracking_views(
    session: Session,
    *,
    symbol: str | None = None,
    prediction_id: int | None = None,
    horizon_days: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[RecommendationTrackingView, ...]:
    """Inspect tracking views filtered by stock, recommendation, horizon,
    and/or date (AC: "users can inspect outcome history by stock,
    recommendation, horizon, and date"). Historical (completed)
    recommendations remain fully viewable alongside active ones -- there is
    no filter on `Prediction.status` here at all (AC: "historical
    recommendations remain viewable after completion")."""
    query = select(Prediction)
    if symbol is not None:
        query = query.join(Stock, Stock.id == Prediction.stock_id).where(Stock.symbol == symbol)
    if prediction_id is not None:
        query = query.where(Prediction.id == prediction_id)
    if horizon_days is not None:
        query = query.where(Prediction.horizon_days == horizon_days)
    if start is not None:
        query = query.where(Prediction.as_of_timestamp >= start)
    if end is not None:
        query = query.where(Prediction.as_of_timestamp <= end)
    query = query.order_by(Prediction.as_of_timestamp.asc())

    predictions = session.scalars(query).all()
    return tuple(build_recommendation_tracking_view(session, p) for p in predictions)
