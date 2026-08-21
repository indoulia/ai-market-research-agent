"""EPIC-M1.71: give users a durable history of recommendations, decisions,
feedback, and outcomes so they can evaluate their own investing behavior
alongside system performance.

This module is a composition layer over already-immutable platform
history -- it introduces exactly one new table, `UserDecision` (the one
genuinely new fact this platform does not yet record: what the user
*did* about a recommendation), and otherwise only *reads*:

- M1.66's `RecommendationDecisionTrace` for the recommendation snapshot
  (scope: "record recommendation snapshots linked to user decisions" --
  the snapshot is M1.66's own, not re-captured here).
- M1.52's `RecommendationFeedback` for the user's structured feedback.
- M1.5's `PredictionOutcome` and M1.38's `OutcomeMeasurement` for the
  objective outcome (scope: "show system prediction versus actual
  result").

"User actions and system outcomes are clearly separated" (AC): a
`JournalEntry` keeps `decisions` (this module's own, user-authored table)
and `recommendation_snapshot`/`prediction_vs_actual` (system-computed,
read from other modules' immutable tables) as distinct fields -- never
merged into one ambiguous record.

"Journal data is not used as a production learning signal unless
explicitly passed through the approved learning pipeline" (AC): this
module has no write path to `Prediction`, `ScanCandidate`, or any
scoring/selection table, and no other module in this platform imports
from it -- a `UserDecision` cannot silently influence anything.

"Historical records remain available after recommendation retirement"
(AC): every read here is keyed by `recommendation_generation_id`/
`prediction_id`, never filtered by `Prediction.status` -- a retired
(`EVALUATED`/otherwise) prediction's full journal remains queryable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import OutcomeMeasurement, Prediction, PredictionOutcome, RecommendationDecisionTrace, RecommendationFeedback, UserDecision
from .recommendation_feedback import get_feedback_for_prediction

JOURNAL_RULE_VERSION = "IDJ-001"

DECISION_ACTED_ON = "ACTED_ON"
DECISION_DISMISSED = "DISMISSED"
DECISION_DEFERRED = "DEFERRED"
VALID_DECISIONS = (DECISION_ACTED_ON, DECISION_DISMISSED, DECISION_DEFERRED)

MAX_RATIONALE_LENGTH = 2000


class InvalidDecisionError(ValueError):
    pass


class UserDecisionImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "user_id",
    "recommendation_generation_id",
    "decision",
    "rationale",
    "decided_at",
    "journal_rule_version",
    "created_at",
)


@event.listens_for(UserDecision, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise UserDecisionImmutableError(
            f"user decision {target.id} field(s) {changed} cannot be modified after creation -- record a new decision instead"
        )


@dataclass(frozen=True)
class PredictionVsActual:
    target_return: Decimal | None
    stop_return: Decimal | None
    actual_return: Decimal | None
    outcome: str | None
    outcome_classification: str | None


@dataclass(frozen=True)
class JournalEntry:
    version: str
    user_id: str
    recommendation_generation_id: int
    recommendation_snapshot: RecommendationDecisionTrace | None
    decisions: tuple[UserDecision, ...]
    feedback: tuple[RecommendationFeedback, ...]
    prediction_vs_actual: PredictionVsActual | None


def record_decision(
    session: Session,
    *,
    user_id: str,
    recommendation_generation_id: int,
    decision: str,
    decided_at: datetime,
    rationale: str | None = None,
) -> UserDecision:
    """Always inserts a new row (scope: "preserve historical records
    immutably") -- a user changing their mind about the same
    recommendation records a new decision rather than editing the old
    one, so the full lifecycle stays inspectable."""
    if decision not in VALID_DECISIONS:
        raise InvalidDecisionError(f"decision must be one of {VALID_DECISIONS}, got {decision!r}")
    if rationale is not None and len(rationale) > MAX_RATIONALE_LENGTH:
        raise InvalidDecisionError(f"rationale must be at most {MAX_RATIONALE_LENGTH} characters")

    row = UserDecision(
        user_id=user_id,
        recommendation_generation_id=recommendation_generation_id,
        decision=decision,
        rationale=rationale,
        decided_at=decided_at,
        journal_rule_version=JOURNAL_RULE_VERSION,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_decision_history(
    session: Session, *, user_id: str, recommendation_generation_id: int
) -> tuple[UserDecision, ...]:
    return tuple(
        session.scalars(
            select(UserDecision)
            .where(UserDecision.user_id == user_id, UserDecision.recommendation_generation_id == recommendation_generation_id)
            .order_by(UserDecision.id.asc())
        ).all()
    )


def _prediction_vs_actual(session: Session, prediction_id: int) -> PredictionVsActual | None:
    prediction = session.get(Prediction, prediction_id)
    if prediction is None:
        return None
    outcome = session.scalar(select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction_id))
    measurement = (
        session.scalar(select(OutcomeMeasurement).where(OutcomeMeasurement.prediction_outcome_id == outcome.id))
        if outcome is not None
        else None
    )
    return PredictionVsActual(
        target_return=prediction.target_return,
        stop_return=prediction.stop_return,
        actual_return=outcome.actual_return if outcome is not None else None,
        outcome=outcome.outcome if outcome is not None else None,
        outcome_classification=measurement.outcome_classification if measurement is not None else None,
    )


def get_journal_entry(session: Session, *, user_id: str, recommendation_generation_id: int) -> JournalEntry:
    """Composes the full lifecycle of one recommendation for one user (AC:
    "a user can inspect the full lifecycle of a decision"). Never filters
    by `Prediction.status`, so a retired recommendation's journal remains
    exactly as complete (AC: "historical records remain available after
    recommendation retirement")."""
    snapshot = session.scalar(
        select(RecommendationDecisionTrace).where(
            RecommendationDecisionTrace.recommendation_generation_id == recommendation_generation_id
        )
    )
    decisions = get_decision_history(session, user_id=user_id, recommendation_generation_id=recommendation_generation_id)

    feedback: tuple[RecommendationFeedback, ...] = ()
    prediction_vs_actual: PredictionVsActual | None = None
    if snapshot is not None and snapshot.prediction_id is not None:
        feedback = get_feedback_for_prediction(session, snapshot.prediction_id)
        prediction_vs_actual = _prediction_vs_actual(session, snapshot.prediction_id)

    return JournalEntry(
        version=JOURNAL_RULE_VERSION,
        user_id=user_id,
        recommendation_generation_id=recommendation_generation_id,
        recommendation_snapshot=snapshot,
        decisions=decisions,
        feedback=feedback,
        prediction_vs_actual=prediction_vs_actual,
    )


def get_journal_for_user(session: Session, user_id: str) -> tuple[JournalEntry, ...]:
    """Every recommendation generation this user has ever recorded a
    decision against (scope: "a durable history of recommendations,
    decisions, feedback, and outcomes"), oldest first."""
    generation_ids = session.scalars(
        select(UserDecision.recommendation_generation_id)
        .where(UserDecision.user_id == user_id)
        .distinct()
        .order_by(UserDecision.recommendation_generation_id.asc())
    ).all()
    return tuple(
        get_journal_entry(session, user_id=user_id, recommendation_generation_id=generation_id)
        for generation_id in generation_ids
    )
