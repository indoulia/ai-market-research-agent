"""EPIC-M1.110: classify each prediction through a complete, immutable
lifecycle, and limit the user feed to a controlled, ranked,
deduplicated set of the strongest positive opportunities.

**The lifecycle classification is entirely derived, never a second
state machine**: `classify_prediction_lifecycle_state` reads M1.5's
`PredictionOutcome`, M1.55's `RecommendationRevision` history, M1.62's
`RecommendationRevalidationOutcome`, and M1.15's own `Recommendation
Lifecycle` row -- in that fixed priority order -- and never writes to
any of them. This is the same "derived-classification-never-delete"
pattern this platform already uses for retention/archiving/delisting
(M1.37/M1.96): "archive completed predictions without deleting learning
history" (scope) holds because nothing is ever deleted or hidden, only
classified at read time from already-immutable evidence.

**Capacity control composes M1.87/M1.99's own ranking, never a second
ranking**: `apply_capacity_control` reads the already-persisted
`PositiveOpportunityRanking` rows for a scan (`included=True`, ordered
by `rank_position`) and applies exactly two additional rules on top --
"prevent duplicate active recommendations for the same opportunity/
horizon" (a `(stock_id, horizon_days)` pair already carrying another
prediction currently classified `ACTIVE` excludes any new candidate for
that same pair) and a configurable `capacity_limit` cutoff -- before
persisting one immutable decision per considered prediction. Neither
rule recomputes the ranking itself.

**Keep suppressed/negative candidates internal for learning** (scope)
holds structurally: this module has no write path to `Prediction`,
`RecommendationSelection`, or any recommendation-facing table -- a
prediction excluded by capacity control or classified anything other
than `ACTIVE` is never deleted, only recorded as not currently eligible
for the user feed.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    CapacityControlDecision,
    Prediction,
    PredictionLifecycleSnapshot,
    PredictionOutcome,
    PositiveOpportunityRanking,
    RecommendationGeneration,
    RecommendationLifecycle,
    ScanCandidate,
)
from .recommendation_revalidation import OUTCOME_EXPIRED, OUTCOME_WITHDRAWN, get_revalidation_history
from .recommendation_revision import get_revision_history

LIFECYCLE_CAPACITY_VERSION = "PLC-001"

STATE_CREATED = "CREATED"
STATE_ACTIVE = "ACTIVE"
STATE_REVISED = "REVISED"
STATE_EXPIRED = "EXPIRED"
STATE_TARGET_HIT = "TARGET_HIT"
STATE_SL_HIT = "SL_HIT"
STATE_INVALIDATED = "INVALIDATED"
STATE_EVALUATED = "EVALUATED"

REASON_CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"
REASON_DUPLICATE_ACTIVE_OPPORTUNITY = "DUPLICATE_ACTIVE_OPPORTUNITY"
REASON_SELECTED = "SELECTED"

DEFAULT_CAPACITY_LIMIT = 10


def _generation_for_prediction(session: Session, prediction_id: int) -> RecommendationGeneration | None:
    return session.scalar(select(RecommendationGeneration).where(RecommendationGeneration.prediction_id == prediction_id))


def classify_prediction_lifecycle_state(session: Session, prediction: Prediction) -> tuple[str, str]:
    """Returns `(state, reason)`. Pure and read-only: never writes
    anything. Fixed priority order: a closed, evaluated outcome always
    wins over an open-recommendation signal, which always wins over
    having no lifecycle tracking yet."""
    outcome = session.scalar(select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction.id))
    if outcome is not None:
        if outcome.target_hit:
            return STATE_TARGET_HIT, "prediction outcome evaluated: target hit"
        if outcome.stop_hit:
            return STATE_SL_HIT, "prediction outcome evaluated: stop-loss hit"
        return STATE_EVALUATED, f"prediction outcome evaluated: {outcome.outcome}"

    revalidations = get_revalidation_history(session, prediction.id)
    if revalidations:
        latest = revalidations[-1]
        if latest.outcome == OUTCOME_EXPIRED:
            return STATE_EXPIRED, latest.reason
        if latest.outcome == OUTCOME_WITHDRAWN:
            return STATE_INVALIDATED, latest.reason

    if get_revision_history(session, prediction.id):
        return STATE_REVISED, "at least one immutable revision exists for this prediction"

    generation = _generation_for_prediction(session, prediction.id)
    if generation is not None:
        lifecycle = session.scalar(select(RecommendationLifecycle).where(RecommendationLifecycle.recommendation_generation_id == generation.id))
        if lifecycle is not None:
            return STATE_ACTIVE, f"tracked by M1.15 lifecycle in state {lifecycle.state}"

    return STATE_CREATED, "prediction exists but is not yet tracked by any lifecycle or outcome evidence"


def snapshot_prediction_lifecycle(session: Session, prediction: Prediction, *, evaluated_at: datetime) -> PredictionLifecycleSnapshot:
    """Idempotent by `(prediction_id, evaluated_at)`. `previous_state` is
    read from the most recent prior snapshot for this prediction, so a
    reader can reconstruct every transition without this module ever
    mutating an earlier row (AC-equivalent: "preserve all state
    transitions and reasons")."""
    existing = session.scalar(
        select(PredictionLifecycleSnapshot).where(
            PredictionLifecycleSnapshot.prediction_id == prediction.id, PredictionLifecycleSnapshot.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    state, reason = classify_prediction_lifecycle_state(session, prediction)
    prior = session.scalar(
        select(PredictionLifecycleSnapshot)
        .where(PredictionLifecycleSnapshot.prediction_id == prediction.id)
        .order_by(PredictionLifecycleSnapshot.id.desc())
    )
    previous_state = prior.state if prior is not None else None

    snapshot = PredictionLifecycleSnapshot(
        prediction_id=prediction.id, state=state, previous_state=previous_state, reason=reason,
        evaluated_at=evaluated_at, lifecycle_rule_version=LIFECYCLE_CAPACITY_VERSION,
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def get_lifecycle_history(session: Session, prediction_id: int) -> tuple[PredictionLifecycleSnapshot, ...]:
    return tuple(
        session.scalars(
            select(PredictionLifecycleSnapshot).where(PredictionLifecycleSnapshot.prediction_id == prediction_id).order_by(PredictionLifecycleSnapshot.id.asc())
        ).all()
    )


def _is_currently_active(session: Session, stock_id: int, horizon_days: int, *, exclude_prediction_id: int) -> bool:
    candidates = session.scalars(
        select(Prediction).where(
            Prediction.stock_id == stock_id, Prediction.horizon_days == horizon_days, Prediction.id != exclude_prediction_id,
        )
    ).all()
    for candidate in candidates:
        state, _reason = classify_prediction_lifecycle_state(session, candidate)
        if state == STATE_ACTIVE:
            return True
    return False


def apply_capacity_control(
    session: Session, scan_id: int, *, capacity_limit: int = DEFAULT_CAPACITY_LIMIT, evaluated_at: datetime
) -> tuple[CapacityControlDecision, ...]:
    """Idempotent per `(prediction_id, evaluated_at)`: predictions already
    decided for this `evaluated_at` are returned unchanged. Reads M1.87/
    M1.99's own ranking; never re-ranks anything itself."""
    prediction_ids_in_scan = set(
        session.scalars(
            select(RecommendationGeneration.prediction_id)
            .join(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
            .where(ScanCandidate.scan_id == scan_id, RecommendationGeneration.prediction_id.isnot(None))
        ).all()
    )
    ranked = session.scalars(
        select(PositiveOpportunityRanking)
        .where(
            PositiveOpportunityRanking.evaluated_at == evaluated_at, PositiveOpportunityRanking.included.is_(True),
            PositiveOpportunityRanking.prediction_id.in_(prediction_ids_in_scan),
        )
        .order_by(PositiveOpportunityRanking.rank_position.asc())
    ).all()

    existing = {
        d.prediction_id: d
        for d in session.scalars(
            select(CapacityControlDecision).where(CapacityControlDecision.scan_id == scan_id, CapacityControlDecision.evaluated_at == evaluated_at)
        ).all()
    }
    if existing and len(existing) == len(ranked):
        return tuple(sorted(existing.values(), key=lambda d: d.id))

    decisions: list[CapacityControlDecision] = []
    included_count = 0
    for ranking_row in ranked:
        prediction = session.get(Prediction, ranking_row.prediction_id)
        if _is_currently_active(session, prediction.stock_id, prediction.horizon_days, exclude_prediction_id=prediction.id):
            included, reason = False, REASON_DUPLICATE_ACTIVE_OPPORTUNITY
        elif included_count >= capacity_limit:
            included, reason = False, REASON_CAPACITY_EXCEEDED
        else:
            included, reason = True, REASON_SELECTED
            included_count += 1

        decisions.append(CapacityControlDecision(
            prediction_id=prediction.id, scan_id=scan_id, rank_position=ranking_row.rank_position,
            capacity_limit=capacity_limit, included=included, exclusion_reason=(None if included else reason),
            evaluated_at=evaluated_at, capacity_rule_version=LIFECYCLE_CAPACITY_VERSION,
        ))

    session.add_all(decisions)
    session.commit()
    for decision in decisions:
        session.refresh(decision)
    return tuple(decisions)


def get_capacity_decision_history(session: Session, prediction_id: int) -> tuple[CapacityControlDecision, ...]:
    return tuple(
        session.scalars(
            select(CapacityControlDecision).where(CapacityControlDecision.prediction_id == prediction_id).order_by(CapacityControlDecision.id.asc())
        ).all()
    )
