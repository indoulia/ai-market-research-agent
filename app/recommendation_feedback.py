"""EPIC-M1.52: let users submit structured feedback on recommendation
quality without ever treating that opinion as objective outcome truth.

Deliberately append-only with NO deduplication: unlike almost every other
EPIC in this platform (which is idempotent-by-key -- the same call returns
the same row), `submit_feedback` creates a brand-new row on every call, even
one that looks identical to a prior one. A user can legitimately feel the
same way twice, or feel differently pre- and post-outcome about the same
recommendation; collapsing those into one row would lose real information
(AC: "multiple feedback events are retained"; scope: "pre-outcome and
post-outcome feedback").

`feedback_stage` (`PRE_OUTCOME`/`POST_OUTCOME`) is derived automatically
from whether a `PredictionOutcome` already exists for the prediction at
submission time -- never user-supplied, since the system already knows this
objectively. `model_version` is copied from the immutable `Prediction` row
at submission time, so feedback stays linked to the exact recommendation
version even if a future model change occurs (AC: "feedback is linked to
the exact recommendation version").

This module never reads or writes `PredictionOutcome`/`OutcomeMeasurement`
at all -- there is no code path here that could overwrite an objective
outcome with a user's opinion (AC: "feedback cannot overwrite objective
outcomes").
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import Prediction, PredictionOutcome, RecommendationFeedback

FEEDBACK_RULE_VERSION = "RFB-001"

CATEGORY_TARGET = "TARGET"
CATEGORY_STOP_LOSS = "STOP_LOSS"
CATEGORY_CONFIDENCE = "CONFIDENCE"
CATEGORY_MARKET_CONTEXT = "MARKET_CONTEXT"
CATEGORY_NEWS_EVENTS = "NEWS_EVENTS"
CATEGORY_FUNDAMENTALS = "FUNDAMENTALS"
CATEGORY_OVERALL = "OVERALL"

VALID_CATEGORIES = (
    CATEGORY_TARGET,
    CATEGORY_STOP_LOSS,
    CATEGORY_CONFIDENCE,
    CATEGORY_MARKET_CONTEXT,
    CATEGORY_NEWS_EVENTS,
    CATEGORY_FUNDAMENTALS,
    CATEGORY_OVERALL,
)

REASON_AGREE = "AGREE"
REASON_TOO_HIGH = "TOO_HIGH"
REASON_TOO_LOW = "TOO_LOW"
REASON_WRONG_DIRECTION = "WRONG_DIRECTION"
REASON_MISSING_CONTEXT = "MISSING_CONTEXT"
REASON_OUTDATED_DATA = "OUTDATED_DATA"
REASON_OTHER = "OTHER"

VALID_REASON_CODES = (
    REASON_AGREE,
    REASON_TOO_HIGH,
    REASON_TOO_LOW,
    REASON_WRONG_DIRECTION,
    REASON_MISSING_CONTEXT,
    REASON_OUTDATED_DATA,
    REASON_OTHER,
)

FEEDBACK_STAGE_PRE_OUTCOME = "PRE_OUTCOME"
FEEDBACK_STAGE_POST_OUTCOME = "POST_OUTCOME"

MAX_COMMENT_LENGTH = 2000


class InvalidFeedbackError(ValueError):
    pass


class RecommendationFeedbackImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "user_id",
    "category",
    "reason_code",
    "comment",
    "feedback_stage",
    "model_version",
    "submitted_at",
    "feedback_rule_version",
    "created_at",
)


@event.listens_for(RecommendationFeedback, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise RecommendationFeedbackImmutableError(
            f"recommendation feedback {target.id} field(s) {changed} cannot be modified after creation"
        )


def submit_feedback(
    session: Session,
    prediction: Prediction,
    *,
    user_id: str,
    category: str,
    reason_code: str,
    submitted_at: datetime,
    comment: str | None = None,
) -> RecommendationFeedback:
    """Validates and records one feedback event. Always inserts a new row
    (AC: "multiple feedback events are retained") -- there is no
    idempotency key and no deduplication of any kind."""
    if category not in VALID_CATEGORIES:
        raise InvalidFeedbackError(f"category must be one of {VALID_CATEGORIES}, got {category!r}")
    if reason_code not in VALID_REASON_CODES:
        raise InvalidFeedbackError(f"reason_code must be one of {VALID_REASON_CODES}, got {reason_code!r}")
    if not user_id:
        raise InvalidFeedbackError("user_id must be a non-empty string")
    if comment is not None and len(comment) > MAX_COMMENT_LENGTH:
        raise InvalidFeedbackError(f"comment must be at most {MAX_COMMENT_LENGTH} characters")

    has_outcome = session.scalar(
        select(PredictionOutcome.id).where(PredictionOutcome.prediction_id == prediction.id)
    ) is not None
    feedback_stage = FEEDBACK_STAGE_POST_OUTCOME if has_outcome else FEEDBACK_STAGE_PRE_OUTCOME

    feedback = RecommendationFeedback(
        prediction_id=prediction.id,
        user_id=user_id,
        category=category,
        reason_code=reason_code,
        comment=comment,
        feedback_stage=feedback_stage,
        model_version=prediction.model_version,
        submitted_at=submitted_at,
        feedback_rule_version=FEEDBACK_RULE_VERSION,
    )
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    return feedback


def get_feedback_for_prediction(session: Session, prediction_id: int) -> tuple[RecommendationFeedback, ...]:
    return tuple(
        session.scalars(
            select(RecommendationFeedback)
            .where(RecommendationFeedback.prediction_id == prediction_id)
            .order_by(RecommendationFeedback.id.asc())
        ).all()
    )


def get_feedback_for_user(session: Session, user_id: str) -> tuple[RecommendationFeedback, ...]:
    return tuple(
        session.scalars(
            select(RecommendationFeedback)
            .where(RecommendationFeedback.user_id == user_id)
            .order_by(RecommendationFeedback.id.asc())
        ).all()
    )


def get_feedback_by_category(session: Session, category: str) -> tuple[RecommendationFeedback, ...]:
    return tuple(
        session.scalars(
            select(RecommendationFeedback)
            .where(RecommendationFeedback.category == category)
            .order_by(RecommendationFeedback.id.asc())
        ).all()
    )
