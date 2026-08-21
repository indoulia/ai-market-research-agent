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
