"""DTOs for POST /api/v1/recommendations/{id}/feedback (EPIC-M1.141)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

TYPE_USEFUL = "useful"
TYPE_NOT_USEFUL = "not_useful"
TYPE_TARGET_REALISTIC = "target_realistic"
TYPE_TARGET_TOO_HIGH = "target_too_high"
TYPE_TARGET_TOO_LOW = "target_too_low"
TYPE_REASON = "reason"

VALID_FEEDBACK_TYPES = (
    TYPE_USEFUL,
    TYPE_NOT_USEFUL,
    TYPE_TARGET_REALISTIC,
    TYPE_TARGET_TOO_HIGH,
    TYPE_TARGET_TOO_LOW,
    TYPE_REASON,
)

LEARNING_IMPACT_QUEUED = "queued"
LEARNING_IMPACT_INFORMATIONAL = "informational"


class FeedbackRequest(BaseModel):
    type: str
    comment: str | None = Field(default=None, max_length=2000)
    predictionVersion: str


class FeedbackResponse(BaseModel):
    feedbackId: str
    accepted: bool
    recordedAt: datetime
    learningImpact: str


class FeedbackHistoryItem(BaseModel):
    """One row of ``GET /api/v1/feedback/history`` (EPIC-M3.10).

    Field names follow M3.10's own "Feedback model" list
    (``feedbackId``/``recommendationId``/``predictionVersionId``/
    ``reasonCode``/``note``/``createdAt``) with one deliberate
    substitution: M3.10's illustrative ``rating`` is realized here as
    ``type`` -- the exact ``useful``/``not_useful``/``target_*``/``reason``
    vocabulary EPIC-M1.141 already established for submission (see
    ``VALID_FEEDBACK_TYPES`` above). There is no separate numeric rating
    scale anywhere in this codebase; reusing the real submitted vocabulary
    is honest where inventing a new, unbacked rating enum would not be.
    ``predictionVersionId`` holds the same ``model_version`` string
    accepted by ``FeedbackRequest.predictionVersion``, not a surrogate id
    -- no separate prediction-version id exists.
    """

    feedbackId: str
    recommendationId: int
    predictionVersionId: str
    type: str
    reasonCode: str
    note: str | None
    learningImpact: str
    createdAt: datetime
