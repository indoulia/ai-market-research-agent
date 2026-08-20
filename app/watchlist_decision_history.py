"""EPIC-M1.20: persist the historical decisions produced by M1.19 watchlist
analysis so users and later learning stages can distinguish observation,
qualification, and rejection over time.

Deliberately does not recompute or duplicate any decision logic: this module
only flattens what M1.19's analysis already produced (a `DiscoveryRecord`
tagged `SOURCE_WATCHLIST`, its `RecommendationGeneration`, and -- when
qualifying -- its `Prediction`) into one immutable row purpose-built for
history queries by symbol and time range, rather than requiring every caller
to repeat the same three-way join.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .discovery import SOURCE_WATCHLIST
from .models import DiscoveryRecord, Prediction, RecommendationGeneration, Stock, WatchlistDecision

DECISION_RULE_VERSION = "WDH-001"


class WatchlistDecisionImmutableError(RuntimeError):
    pass


class WatchlistDecisionSourceMissingError(RuntimeError):
    """Raised when the given `RecommendationGeneration` has no matching
    `SOURCE_WATCHLIST` `DiscoveryRecord` -- there is no watchlist-analysis
    provenance to build a decision-history record from."""


IMMUTABLE_FIELDS = (
    "stock_id",
    "symbol",
    "scan_id",
    "recommendation_generation_id",
    "decided_at",
    "outcome",
    "failed_criteria",
    "consensus_contract_version",
    "prediction_id",
    "model_version",
    "feature_version",
    "scoring_contract_version",
    "horizon_selection_version",
    "opportunity_score",
    "decision_rule_version",
    "created_at",
)


@event.listens_for(WatchlistDecision, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise WatchlistDecisionImmutableError(
            f"watchlist decision {target.id} field(s) {changed} cannot be modified after creation"
        )


def record_watchlist_decision(
    session: Session, generation: RecommendationGeneration
) -> WatchlistDecision:
    """Flatten one M1.19 watchlist analysis result into an immutable history
    row. Idempotent by `recommendation_generation_id` uniqueness: calling this
    twice for the same generation returns the original row unchanged."""
    existing = session.scalar(
        select(WatchlistDecision).where(
            WatchlistDecision.recommendation_generation_id == generation.id
        )
    )
    if existing is not None:
        return existing

    discovery = session.scalar(
        select(DiscoveryRecord).where(
            DiscoveryRecord.recommendation_generation_id == generation.id,
            DiscoveryRecord.source == SOURCE_WATCHLIST,
        )
    )
    if discovery is None:
        raise WatchlistDecisionSourceMissingError(
            f"recommendation generation {generation.id} has no {SOURCE_WATCHLIST} "
            "discovery record; it was not produced by watchlist analysis"
        )

    prediction = session.get(Prediction, generation.prediction_id) if generation.prediction_id else None

    decision = WatchlistDecision(
        stock_id=discovery.stock_id,
        symbol=_symbol_for(session, discovery.stock_id),
        scan_id=discovery.scan_id,
        recommendation_generation_id=generation.id,
        decided_at=discovery.discovered_at,
        outcome=generation.outcome,
        failed_criteria=generation.failed_criteria,
        consensus_contract_version=generation.consensus_contract_version,
        prediction_id=generation.prediction_id,
        model_version=prediction.model_version if prediction else None,
        feature_version=prediction.feature_version if prediction else None,
        scoring_contract_version=prediction.scoring_contract_version if prediction else None,
        horizon_selection_version=prediction.horizon_selection_version if prediction else None,
        opportunity_score=prediction.opportunity_score if prediction else None,
        decision_rule_version=DECISION_RULE_VERSION,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def _symbol_for(session: Session, stock_id: int) -> str:
    return session.get(Stock, stock_id).symbol


def get_watchlist_decision_history(
    session: Session,
    *,
    stock_id: int | None = None,
    symbol: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[WatchlistDecision, ...]:
    """Deterministic history query: ordered by `decided_at` ascending, then
    `id`, optionally filtered by stock/symbol and an inclusive time range."""
    query = select(WatchlistDecision)
    if stock_id is not None:
        query = query.where(WatchlistDecision.stock_id == stock_id)
    if symbol is not None:
        query = query.where(WatchlistDecision.symbol == symbol)
    if start is not None:
        query = query.where(WatchlistDecision.decided_at >= start)
    if end is not None:
        query = query.where(WatchlistDecision.decided_at <= end)
    query = query.order_by(WatchlistDecision.decided_at.asc(), WatchlistDecision.id.asc())
    return tuple(session.scalars(query).all())
