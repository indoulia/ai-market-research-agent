"""EPIC-M1.15: automatically track each M1.14-selected recommendation through its
selected 1/3/5/7 trading-day horizon (app/horizon.py) and evaluate its objective
outcome (app/outcomes.py) without manual intervention. This module wraps M1.5's
per-prediction evaluator with a persisted, idempotent, interruption-recoverable
lifecycle state per recommendation -- it never changes how an outcome is computed,
only when/whether it has been checked.

Weekends and market holidays need no special handling here: `evaluate_recommendation`
counts actual `MarketPrice` trading-session rows after issuance rather than calendar
days, so non-trading days are already absent from that count.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Prediction,
    PredictionOutcome,
    RecommendationGeneration,
    RecommendationLifecycle,
    RecommendationSelection,
)
from .outcomes import RecommendationAlreadyEvaluatedError, evaluate_recommendation

LIFECYCLE_VERSION = "RLS-001"

STATE_ISSUED = "ISSUED"
STATE_AWAITING_HORIZON = "AWAITING_HORIZON"
STATE_EVALUATED = "EVALUATED"
STATE_UNEVALUABLE = "UNEVALUABLE"

# Terminal states are never processed again -- this is what makes `process_due_lifecycles`
# idempotent and safe to resume after an interruption.
OPEN_STATES = (STATE_ISSUED, STATE_AWAITING_HORIZON)
TERMINAL_STATES = (STATE_EVALUATED, STATE_UNEVALUABLE)


def ensure_lifecycle_entries_for_scan(session: Session, scan_id: int) -> tuple[RecommendationLifecycle, ...]:
    """Create an `ISSUED` lifecycle row for every selected recommendation in
    `scan_id` that doesn't already have one. Idempotent: a recommendation already
    tracked (unique on `recommendation_generation_id`) is left untouched and simply
    included in the returned set, in the scan's selection order."""
    selected_generation_ids = session.scalars(
        select(RecommendationSelection.recommendation_generation_id).where(
            RecommendationSelection.scan_id == scan_id,
            RecommendationSelection.selected.is_(True),
        )
    ).all()
    if not selected_generation_ids:
        return ()

    existing_ids = set(
        session.scalars(
            select(RecommendationLifecycle.recommendation_generation_id).where(
                RecommendationLifecycle.recommendation_generation_id.in_(selected_generation_ids)
            )
        ).all()
    )

    created = False
    for generation_id in selected_generation_ids:
        if generation_id in existing_ids:
            continue
        session.add(
            RecommendationLifecycle(
                recommendation_generation_id=generation_id,
                state=STATE_ISSUED,
                lifecycle_rule_version=LIFECYCLE_VERSION,
            )
        )
        created = True
    if created:
        session.commit()

    rows = session.scalars(
        select(RecommendationLifecycle).where(
            RecommendationLifecycle.recommendation_generation_id.in_(selected_generation_ids)
        )
    ).all()
    order = {generation_id: index for index, generation_id in enumerate(selected_generation_ids)}
    rows.sort(key=lambda row: order[row.recommendation_generation_id])
    return tuple(rows)


def advance_lifecycle(session: Session, lifecycle: RecommendationLifecycle) -> RecommendationLifecycle:
    """Check one lifecycle row against the current outcome-evaluation contract and
    persist the result. A no-op for a row already in a terminal state, so callers
    don't need to filter before calling it directly."""
    if lifecycle.state in TERMINAL_STATES:
        return lifecycle

    generation = session.get(RecommendationGeneration, lifecycle.recommendation_generation_id)
    prediction = session.get(Prediction, generation.prediction_id)

    try:
        outcome = evaluate_recommendation(session, prediction)
    except RecommendationAlreadyEvaluatedError:
        outcome = session.scalars(
            select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction.id)
        ).one()

    lifecycle.check_count += 1
    lifecycle.last_checked_at = datetime.now(timezone.utc)
    if outcome is None:
        lifecycle.state = STATE_AWAITING_HORIZON
    elif outcome.outcome == "UNEVALUABLE":
        lifecycle.state = STATE_UNEVALUABLE
        lifecycle.outcome_id = outcome.id
    else:
        lifecycle.state = STATE_EVALUATED
        lifecycle.outcome_id = outcome.id

    session.commit()
    session.refresh(lifecycle)
    return lifecycle


def process_due_lifecycles(
    session: Session, *, scan_id: int | None = None
) -> tuple[RecommendationLifecycle, ...]:
    """Advance every non-terminal lifecycle row, optionally scoped to one scan. This
    is the scheduler's entry point: safe on any cadence and safe to resume after an
    interruption, since a row that already reached `EVALUATED`/`UNEVALUABLE` on a
    prior run is excluded from the query, not merely skipped once loaded."""
    query = select(RecommendationLifecycle).where(RecommendationLifecycle.state.in_(OPEN_STATES))
    if scan_id is not None:
        query = query.where(
            RecommendationLifecycle.recommendation_generation_id.in_(
                select(RecommendationSelection.recommendation_generation_id).where(
                    RecommendationSelection.scan_id == scan_id
                )
            )
        )
    rows = session.scalars(query.order_by(RecommendationLifecycle.id)).all()
    return tuple(advance_lifecycle(session, row) for row in rows)
