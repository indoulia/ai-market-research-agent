"""Service backing POST /api/v1/recommendations/{id}/feedback (EPIC-M1.141).

Composes M1.52's `app.recommendation_feedback.submit_feedback` (append-
only, deliberately non-idempotent by design -- see that module's own
docstring) with an API-layer idempotency key so a client retry doesn't
create a second feedback event (AC: "duplicate submissions are
idempotent where client request ID is reused").

The API's single `type` enum maps onto the domain's
`(category, reason_code)` pair -- a translation this layer owns, not the
domain module (there is no 1:1 domain vocabulary for "useful"/"reason").
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FeedbackIdempotencyKey, Prediction, RecommendationFeedback, RecommendationGeneration
from app.recommendation_feedback import (
    CATEGORY_OVERALL,
    CATEGORY_TARGET,
    REASON_AGREE,
    REASON_OTHER,
    REASON_TOO_HIGH,
    REASON_TOO_LOW,
    InvalidFeedbackError,
    submit_feedback,
)
from app.recommendation_revision import get_active_version

from ..errors import ConflictError, NotFoundError, ValidationError
from ..schemas.feedback import (
    LEARNING_IMPACT_INFORMATIONAL,
    LEARNING_IMPACT_QUEUED,
    TYPE_NOT_USEFUL,
    TYPE_REASON,
    TYPE_TARGET_REALISTIC,
    TYPE_TARGET_TOO_HIGH,
    TYPE_TARGET_TOO_LOW,
    TYPE_USEFUL,
    VALID_FEEDBACK_TYPES,
    FeedbackRequest,
    FeedbackResponse,
)

_TYPE_TO_CATEGORY_REASON = {
    TYPE_USEFUL: (CATEGORY_OVERALL, REASON_AGREE),
    TYPE_NOT_USEFUL: (CATEGORY_OVERALL, REASON_OTHER),
    TYPE_TARGET_REALISTIC: (CATEGORY_TARGET, REASON_AGREE),
    TYPE_TARGET_TOO_HIGH: (CATEGORY_TARGET, REASON_TOO_HIGH),
    TYPE_TARGET_TOO_LOW: (CATEGORY_TARGET, REASON_TOO_LOW),
    TYPE_REASON: (CATEGORY_OVERALL, REASON_OTHER),
}

_QUEUED_TYPES = frozenset({TYPE_TARGET_REALISTIC, TYPE_TARGET_TOO_HIGH, TYPE_TARGET_TOO_LOW})


def submit_recommendation_feedback(
    session: Session,
    recommendation_id: int,
    request: FeedbackRequest,
    *,
    user_id: str,
    submitted_at: datetime,
    idempotency_key: str | None,
) -> FeedbackResponse:
    if request.type not in VALID_FEEDBACK_TYPES:
        raise ValidationError(f"type must be one of {VALID_FEEDBACK_TYPES}, got {request.type!r}", field_errors={"type": f"must be one of {VALID_FEEDBACK_TYPES}"})

    generation = session.get(RecommendationGeneration, recommendation_id)
    if generation is None or generation.prediction_id is None:
        raise NotFoundError("Recommendation", str(recommendation_id))

    original = session.get(Prediction, generation.prediction_id)
    active = get_active_version(session, original)
    if request.predictionVersion != active.model_version:
        raise ConflictError(
            "MRA_STALE_PREDICTION_VERSION",
            f"predictionVersion {request.predictionVersion!r} is stale; current version is {active.model_version!r}.",
            details={"currentVersion": active.model_version},
        )

    if idempotency_key:
        existing_key = session.scalar(
            select(FeedbackIdempotencyKey).where(
                FeedbackIdempotencyKey.user_id == user_id, FeedbackIdempotencyKey.idempotency_key == idempotency_key,
            )
        )
        if existing_key is not None:
            existing_feedback = session.get(RecommendationFeedback, existing_key.feedback_id)
            return _to_response(existing_feedback, request.type)

    category, reason_code = _TYPE_TO_CATEGORY_REASON[request.type]
    try:
        feedback = submit_feedback(
            session, active, user_id=user_id, category=category, reason_code=reason_code,
            submitted_at=submitted_at, comment=request.comment,
        )
    except InvalidFeedbackError as exc:
        raise ValidationError(str(exc)) from exc

    if idempotency_key:
        session.add(FeedbackIdempotencyKey(user_id=user_id, idempotency_key=idempotency_key, feedback_id=feedback.id))
        session.commit()

    return _to_response(feedback, request.type)


def _to_response(feedback: RecommendationFeedback, feedback_type: str) -> FeedbackResponse:
    learning_impact = LEARNING_IMPACT_QUEUED if feedback_type in _QUEUED_TYPES else LEARNING_IMPACT_INFORMATIONAL
    return FeedbackResponse(
        feedbackId=str(feedback.id), accepted=True, recordedAt=feedback.submitted_at, learningImpact=learning_impact,
    )
