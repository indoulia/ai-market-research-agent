"""EPIC-M1.55: allow a live recommendation to be revised when material new
information changes the system's view, while preserving every prior version
and its original prediction untouched.

`Prediction` rows are already immutable (M1.4/M1.13's own guard); this
module never mutates one. A "revision" is always a brand-new `Prediction`,
built through the exact same M1.9/M1.10/M1.13 pipeline with fresh inputs by
whatever caller decides a revision is warranted (e.g. M1.54's revalidation
trigger) -- this module's only job is to link that new prediction as the
next version of an existing recommendation, never to (re)compute scoring
itself. "New target, SL, horizon, score, confidence, and evidence snapshot
when revised" (scope) therefore falls out for free: the revised `Prediction`
already carries its own real horizon/score/confidence, and a caller can
independently run M1.47 (target/SL) and M1.48 (evidence snapshot) against it
exactly as for any other prediction -- no special-cased logic needed here.

The version chain is kept strictly linear by a uniqueness constraint on
`previous_prediction_id`: a prediction can be superseded by at most one next
version. Calling `create_recommendation_revision` again with the identical
(previous, revised) pair is idempotent (AC: covers "duplicate ... triggers");
calling it again for the same previous prediction with a *different*
revised prediction raises `ConcurrentRevisionError` rather than silently
branching the chain (AC: covers "concurrent ... triggers").

Because each version is a genuinely separate `Prediction` row, M1.5's
outcome evaluation, M1.36's tracking, and M1.48's evidence snapshot already
associate correctly with whichever version they were run against -- "preserve
original and previous outcomes/history" and "tracking associates outcomes
with the correct version" (AC) require no new code here at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import Prediction, RecommendationRevision

REVISION_RULE_VERSION = "RRV-001"

REASON_MATERIAL_EVIDENCE_CHANGE = "MATERIAL_EVIDENCE_CHANGE"
REASON_EVIDENCE_STALE = "EVIDENCE_STALE"
REASON_MANUAL_TRIGGER = "MANUAL_TRIGGER"

VALID_REVISION_REASONS = (REASON_MATERIAL_EVIDENCE_CHANGE, REASON_EVIDENCE_STALE, REASON_MANUAL_TRIGGER)


class InvalidRevisionError(ValueError):
    pass


class ConcurrentRevisionError(RuntimeError):
    """Raised when a prediction already has a different next version than
    the one being submitted -- the version chain must stay strictly linear,
    never branching."""


class RecommendationRevisionImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "original_prediction_id",
    "previous_prediction_id",
    "revised_prediction_id",
    "version_number",
    "revision_reason",
    "triggering_evidence_revalidation_check_id",
    "revised_at",
    "revision_rule_version",
    "created_at",
)


@event.listens_for(RecommendationRevision, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise RecommendationRevisionImmutableError(
            f"recommendation revision {target.id} field(s) {changed} cannot be modified after creation"
        )


@dataclass(frozen=True)
class VersionComparison:
    previous_prediction_id: int
    revised_prediction_id: int
    opportunity_score_delta: Decimal
    confidence_delta: Decimal
    predicted_probability_delta: Decimal
    target_return_delta: Decimal
    stop_return_delta: Decimal
    previous_horizon_days: int
    revised_horizon_days: int
    horizon_changed: bool


def get_revision_history(session: Session, original_prediction_id: int) -> tuple[RecommendationRevision, ...]:
    """Full, immutable, version-ordered revision chain (AC: "revisions are
    deterministic and auditable")."""
    return tuple(
        session.scalars(
            select(RecommendationRevision)
            .where(RecommendationRevision.original_prediction_id == original_prediction_id)
            .order_by(RecommendationRevision.version_number.asc())
        ).all()
    )


def get_active_version(session: Session, original_prediction: Prediction) -> Prediction:
    """The most recent revision's prediction, or the original itself if
    never revised (AC: "clear active version for users")."""
    history = get_revision_history(session, original_prediction.id)
    if not history:
        return original_prediction
    return session.get(Prediction, history[-1].revised_prediction_id)


def compare_versions(session: Session, revision: RecommendationRevision) -> VersionComparison:
    """Version-to-version comparison (AC: "users can see what changed and
    why" -- combined with `revision.revision_reason`)."""
    previous = session.get(Prediction, revision.previous_prediction_id)
    revised = session.get(Prediction, revision.revised_prediction_id)
    return VersionComparison(
        previous_prediction_id=previous.id,
        revised_prediction_id=revised.id,
        opportunity_score_delta=revised.opportunity_score - previous.opportunity_score,
        confidence_delta=revised.confidence - previous.confidence,
        predicted_probability_delta=revised.predicted_probability - previous.predicted_probability,
        target_return_delta=revised.target_return - previous.target_return,
        stop_return_delta=revised.stop_return - previous.stop_return,
        previous_horizon_days=previous.horizon_days,
        revised_horizon_days=revised.horizon_days,
        horizon_changed=previous.horizon_days != revised.horizon_days,
    )


def create_recommendation_revision(
    session: Session,
    *,
    original_prediction: Prediction,
    previous_prediction: Prediction,
    revised_prediction: Prediction,
    revision_reason: str,
    revised_at: datetime,
    triggering_evidence_revalidation_check_id: int | None = None,
) -> RecommendationRevision:
    """Links `revised_prediction` as the next version after
    `previous_prediction` in `original_prediction`'s chain. Idempotent for
    the identical `(previous_prediction, revised_prediction)` pair (AC:
    duplicate triggers); raises `ConcurrentRevisionError` if
    `previous_prediction` already has a *different* next version (AC:
    concurrent triggers) -- the chain never branches."""
    if revision_reason not in VALID_REVISION_REASONS:
        raise InvalidRevisionError(f"revision_reason must be one of {VALID_REVISION_REASONS}, got {revision_reason!r}")
    if revised_prediction.stock_id != previous_prediction.stock_id:
        raise InvalidRevisionError("a revision must be for the same underlying stock as the version it supersedes")

    existing = session.scalar(
        select(RecommendationRevision).where(RecommendationRevision.previous_prediction_id == previous_prediction.id)
    )
    if existing is not None:
        if existing.revised_prediction_id == revised_prediction.id:
            return existing
        raise ConcurrentRevisionError(
            f"prediction {previous_prediction.id} already has a different next version "
            f"({existing.revised_prediction_id}); the revision chain must stay linear"
        )

    prior_versions = get_revision_history(session, original_prediction.id)
    version_number = len(prior_versions) + 2  # version 1 is the original itself

    revision = RecommendationRevision(
        original_prediction_id=original_prediction.id,
        previous_prediction_id=previous_prediction.id,
        revised_prediction_id=revised_prediction.id,
        version_number=version_number,
        revision_reason=revision_reason,
        triggering_evidence_revalidation_check_id=triggering_evidence_revalidation_check_id,
        revised_at=revised_at,
        revision_rule_version=REVISION_RULE_VERSION,
    )
    session.add(revision)
    session.commit()
    session.refresh(revision)
    return revision
