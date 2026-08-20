"""EPIC-M1.37: automatically close a recommendation when its lifecycle ends
and make it queryable as archived history, without ever deleting evidence.

Overlays four business-facing states on top of M1.15's internal lifecycle
(`ISSUED`/`AWAITING_HORIZON`/`EVALUATED`/`UNEVALUABLE`):

- `ACTIVE` -- M1.15's `OPEN_STATES`, or no lifecycle row at all yet.
- `COMPLETED` -- M1.15's `TERMINAL_STATES` reached, but not yet retired.
- `RETIRED` -- an explicit, immutable retirement event has been recorded.
- `ARCHIVED` -- a *derived* classification: a retired recommendation whose
  retention window has elapsed. This is deliberately not a second persisted
  state -- "archiving" never moves or deletes a row, it only changes how an
  already-retired recommendation is classified at query time, so "keep
  archived records queryable" and "never delete recommendation evidence"
  both hold by construction rather than by a second table's consistency.

Nothing in this module writes to `Prediction`, `RecommendationGeneration`, or
`RecommendationLifecycle` -- it only reads M1.15's lifecycle state and adds
its own new, immutable `RecommendationRetirement` row.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .lifecycle import OPEN_STATES, TERMINAL_STATES
from .models import Prediction, RecommendationGeneration, RecommendationLifecycle, RecommendationRetirement

RETIREMENT_RULE_VERSION = "RET-001"

STATUS_ACTIVE = "ACTIVE"
STATUS_COMPLETED = "COMPLETED"
STATUS_RETIRED = "RETIRED"
STATUS_ARCHIVED = "ARCHIVED"

REASON_HORIZON_COMPLETED = "HORIZON_COMPLETED"

# Fixed, documented, versioned policy constant: how long a recommendation
# stays merely "retired" before it is classified "archived" at query time.
DEFAULT_ARCHIVE_RETENTION = timedelta(days=90)


class RecommendationNotCompletedError(RuntimeError):
    """Raised when attempting to retire a recommendation whose M1.15
    lifecycle has not reached a terminal state yet -- retirement only
    happens at deterministic horizon completion, never before."""


class RecommendationRetirementImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "retired_at",
    "retirement_reason",
    "lifecycle_state_at_retirement",
    "retirement_rule_version",
    "created_at",
)


@event.listens_for(RecommendationRetirement, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise RecommendationRetirementImmutableError(
            f"recommendation retirement {target.id} field(s) {changed} cannot be modified after creation"
        )


def retire_recommendation(
    session: Session, lifecycle: RecommendationLifecycle, *, retired_at: datetime
) -> RecommendationRetirement:
    """Retire the recommendation behind `lifecycle`. Raises
    `RecommendationNotCompletedError` if the lifecycle hasn't reached a
    terminal state (AC: "recommendations retire automatically at the correct
    horizon" -- never before). Idempotent by `prediction_id` uniqueness: a
    recommendation already retired returns its original, immutable
    retirement event unchanged (AC: "archive operations are idempotent")."""
    if lifecycle.state not in TERMINAL_STATES:
        raise RecommendationNotCompletedError(
            f"lifecycle {lifecycle.id} is not yet in a terminal state ({lifecycle.state}); cannot retire"
        )

    generation = session.get(RecommendationGeneration, lifecycle.recommendation_generation_id)
    prediction_id = generation.prediction_id

    existing = session.scalar(
        select(RecommendationRetirement).where(RecommendationRetirement.prediction_id == prediction_id)
    )
    if existing is not None:
        return existing

    retirement = RecommendationRetirement(
        prediction_id=prediction_id,
        retired_at=retired_at,
        retirement_reason=REASON_HORIZON_COMPLETED,
        lifecycle_state_at_retirement=lifecycle.state,
        retirement_rule_version=RETIREMENT_RULE_VERSION,
    )
    session.add(retirement)
    session.commit()
    session.refresh(retirement)
    return retirement


def get_recommendation_status(
    session: Session, prediction_id: int, *, now: datetime, archive_retention: timedelta = DEFAULT_ARCHIVE_RETENTION
) -> str:
    """The single source of truth for a recommendation's business-facing
    state. A prediction with no `RecommendationLifecycle` row at all is
    treated as `ACTIVE` -- there is no evidence yet that it has completed."""
    lifecycle = session.scalar(
        select(RecommendationLifecycle)
        .join(RecommendationGeneration, RecommendationGeneration.id == RecommendationLifecycle.recommendation_generation_id)
        .where(RecommendationGeneration.prediction_id == prediction_id)
    )
    if lifecycle is None or lifecycle.state in OPEN_STATES:
        return STATUS_ACTIVE

    retirement = session.scalar(
        select(RecommendationRetirement).where(RecommendationRetirement.prediction_id == prediction_id)
    )
    if retirement is None:
        return STATUS_COMPLETED

    # sqlite drops tzinfo on DateTime(timezone=True) round-trips, unlike
    # Postgres; every timestamp in this system is UTC-based by convention, so
    # comparing naively is correct regardless of which backend produced it.
    if now.replace(tzinfo=None) - retirement.retired_at.replace(tzinfo=None) >= archive_retention:
        return STATUS_ARCHIVED
    return STATUS_RETIRED


def get_active_prediction_ids(session: Session) -> tuple[int, ...]:
    """Every `Prediction` id currently `ACTIVE` -- excludes anything with a
    terminal M1.15 lifecycle state, regardless of whether it has been
    formally retired yet (AC: "active views exclude retired/archived
    recommendations," and expired-but-not-yet-retired recommendations must
    not appear active either)."""
    non_active_ids = set(
        session.scalars(
            select(RecommendationGeneration.prediction_id)
            .join(RecommendationLifecycle, RecommendationLifecycle.recommendation_generation_id == RecommendationGeneration.id)
            .where(RecommendationLifecycle.state.in_(TERMINAL_STATES))
        ).all()
    )
    all_ids = set(
        session.scalars(select(RecommendationGeneration.prediction_id).where(RecommendationGeneration.prediction_id.isnot(None))).all()
    )
    return tuple(sorted(all_ids - non_active_ids))


def get_archived_retirements(
    session: Session, *, now: datetime, archive_retention: timedelta = DEFAULT_ARCHIVE_RETENTION
) -> tuple[RecommendationRetirement, ...]:
    """Every retired recommendation whose retention window has elapsed --
    fully queryable, nothing deleted or moved (scope: "keep archived records
    queryable")."""
    cutoff = now - archive_retention
    return tuple(
        session.scalars(
            select(RecommendationRetirement)
            .where(RecommendationRetirement.retired_at <= cutoff)
            .order_by(RecommendationRetirement.retired_at.asc())
        ).all()
    )
