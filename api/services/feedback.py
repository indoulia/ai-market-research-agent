"""Service backing POST /api/v1/recommendations/{id}/feedback (EPIC-M1.141)
and GET /api/v1/feedback/history (EPIC-M3.10).

Composes M1.52's `app.recommendation_feedback.submit_feedback` (append-
only, deliberately non-idempotent by design -- see that module's own
docstring) with an API-layer idempotency key so a client retry doesn't
create a second feedback event (AC: "duplicate submissions are
idempotent where client request ID is reused").

The API's single `type` enum maps onto the domain's
`(category, reason_code)` pair -- a translation this layer owns, not the
domain module (there is no 1:1 domain vocabulary for "useful"/"reason").
`get_feedback_history` reverses that same translation (best-effort --
see `_CATEGORY_REASON_TO_TYPE`'s docstring for the one lossy case) to
list a caller's own past submissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    FeedbackIdempotencyKey,
    Prediction,
    RecommendationFeedback,
    RecommendationGeneration,
    RecommendationRevision,
)
from app.recommendation_feedback import (
    CATEGORY_OVERALL,
    CATEGORY_TARGET,
    REASON_AGREE,
    REASON_OTHER,
    REASON_TOO_HIGH,
    REASON_TOO_LOW,
    InvalidFeedbackError,
    get_feedback_for_user,
    submit_feedback,
)
from app.recommendation_revision import get_active_version

from ..errors import ConflictError, NotFoundError, ValidationError
from ..pagination import DEFAULT_PAGE_SIZE, decode_offset_cursor, encode_offset_cursor
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
    FeedbackHistoryItem,
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

# Reverse of `_TYPE_TO_CATEGORY_REASON`, for `GET /feedback/history`
# (EPIC-M3.10). Lossy by construction: `TYPE_NOT_USEFUL` and `TYPE_REASON`
# both submit as `(CATEGORY_OVERALL, REASON_OTHER)`, since the domain model
# (EPIC-M1.52) never stores the API's `type` string itself -- only
# `category`/`reason_code`. `(OVERALL, OTHER)` is reported back as
# `not_useful` (the more common of the two); a row submitted as `reason`
# with no comment is indistinguishable from `not_useful` on read-back. Any
# `(category, reason_code)` pair the API's own `type` vocabulary never
# produces (e.g. a future caller of `app.recommendation_feedback.
# submit_feedback` using `CATEGORY_CONFIDENCE` directly) falls back to
# `TYPE_REASON` rather than raising -- this is a read-only projection and
# must never fail on data it didn't itself create.
_CATEGORY_REASON_TO_TYPE = {
    (CATEGORY_OVERALL, REASON_AGREE): TYPE_USEFUL,
    (CATEGORY_OVERALL, REASON_OTHER): TYPE_NOT_USEFUL,
    (CATEGORY_TARGET, REASON_AGREE): TYPE_TARGET_REALISTIC,
    (CATEGORY_TARGET, REASON_TOO_HIGH): TYPE_TARGET_TOO_HIGH,
    (CATEGORY_TARGET, REASON_TOO_LOW): TYPE_TARGET_TOO_LOW,
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


def _recommendation_id_for_prediction(session: Session, prediction_id: int) -> int | None:
    """Reverses M1.52's `prediction_id` (the *version* a feedback row was
    submitted against, which may be a revision -- see `submit_feedback`'s
    `active` argument) back to the stable `RecommendationGeneration.id`
    used in URLs (`recommendationId`). A `RecommendationGeneration` always
    points at version 1 (the original prediction); `RecommendationRevision.
    original_prediction_id` gives the same original id for any later
    version. Returns `None` only if the recommendation itself was deleted
    out from under an otherwise-valid feedback row."""
    generation_id = session.scalar(
        select(RecommendationGeneration.id).where(RecommendationGeneration.prediction_id == prediction_id)
    )
    if generation_id is not None:
        return generation_id

    original_prediction_id = session.scalar(
        select(RecommendationRevision.original_prediction_id).where(
            RecommendationRevision.revised_prediction_id == prediction_id
        )
    )
    if original_prediction_id is None:
        return None
    return session.scalar(
        select(RecommendationGeneration.id).where(RecommendationGeneration.prediction_id == original_prediction_id)
    )


@dataclass
class FeedbackHistoryPage:
    items: list[FeedbackHistoryItem]
    next_cursor: str | None


def get_feedback_history(
    session: Session, *, user_id: str, cursor: str | None = None, page_size: int = DEFAULT_PAGE_SIZE
) -> FeedbackHistoryPage:
    """`GET /api/v1/feedback/history` (EPIC-M3.10): every feedback event
    the caller has ever submitted, newest first. Read-only projection over
    M1.52's append-only `RecommendationFeedback` table -- nothing here can
    mutate a past submission (AC: "feedback is immutable after
    submission")."""
    all_feedback = sorted(
        get_feedback_for_user(session, user_id), key=lambda f: (f.submitted_at, f.id), reverse=True
    )

    offset = decode_offset_cursor(cursor) if cursor else 0
    page = all_feedback[offset : offset + page_size]

    items = []
    for feedback in page:
        recommendation_id = _recommendation_id_for_prediction(session, feedback.prediction_id)
        if recommendation_id is None:
            continue
        feedback_type = _CATEGORY_REASON_TO_TYPE.get((feedback.category, feedback.reason_code), TYPE_REASON)
        items.append(
            FeedbackHistoryItem(
                feedbackId=str(feedback.id),
                recommendationId=recommendation_id,
                predictionVersionId=feedback.model_version,
                type=feedback_type,
                reasonCode=feedback.reason_code,
                note=feedback.comment,
                learningImpact=(
                    LEARNING_IMPACT_QUEUED if feedback_type in _QUEUED_TYPES else LEARNING_IMPACT_INFORMATIONAL
                ),
                createdAt=feedback.submitted_at,
            )
        )

    next_cursor = encode_offset_cursor(offset + page_size) if offset + page_size < len(all_feedback) else None
    return FeedbackHistoryPage(items=items, next_cursor=next_cursor)
