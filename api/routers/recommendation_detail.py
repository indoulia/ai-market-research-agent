"""GET /api/v1/recommendations/{recommendationId}[/history|/events|/outcome] (EPIC-M1.137)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from ..deps import get_db, require_bearer_subject
from ..envelope import cursor_paginated, success
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope, SuccessEnvelope
from ..schemas.feedback import FeedbackRequest, FeedbackResponse
from ..schemas.recommendation_detail import EventItem, EvidenceResponse, HistoryItem, OutcomeResponse, RecommendationDetail, TimelineItem
from ..services.feedback import submit_recommendation_feedback
from ..services.recommendation_detail import get_detail, get_evidence, get_events, get_history, get_outcome, get_timeline

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/{recommendationId}", response_model=SuccessEnvelope[RecommendationDetail])
def get_recommendation_detail(recommendationId: int, db: Session = Depends(get_db)):
    return success(get_detail(db, recommendationId))


@router.get("/{recommendationId}/history", response_model=CursorEnvelope[HistoryItem])
def get_recommendation_history(
    recommendationId: int,
    db: Session = Depends(get_db),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = get_history(db, recommendationId, from_ts=from_, to_ts=to, cursor=cursor, page_size=pageSize)
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)


@router.get("/{recommendationId}/events", response_model=CursorEnvelope[EventItem])
def get_recommendation_events(
    recommendationId: int,
    db: Session = Depends(get_db),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = get_events(db, recommendationId, cursor=cursor, page_size=pageSize)
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)


@router.get("/{recommendationId}/timeline", response_model=SuccessEnvelope[list[TimelineItem]])
def get_recommendation_timeline(recommendationId: int, db: Session = Depends(get_db)):
    """EPIC-M3.4: the full, ordered prediction-version timeline (original
    + every revision), each with its reason and affected metrics."""
    return success(get_timeline(db, recommendationId))


@router.get("/{recommendationId}/evidence", response_model=SuccessEnvelope[EvidenceResponse])
def get_recommendation_evidence(recommendationId: int, db: Session = Depends(get_db)):
    """EPIC-M3.4: fundamental/technical/market/news/event evidence plus
    provider provenance, as their own contract."""
    return success(get_evidence(db, recommendationId))


@router.get("/{recommendationId}/outcome", response_model=SuccessEnvelope[OutcomeResponse])
def get_recommendation_outcome(recommendationId: int, db: Session = Depends(get_db)):
    return success(get_outcome(db, recommendationId))


@router.post("/{recommendationId}/feedback", response_model=SuccessEnvelope[FeedbackResponse])
def post_recommendation_feedback(
    recommendationId: int,
    request: FeedbackRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(require_bearer_subject),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    response = submit_recommendation_feedback(
        db, recommendationId, request, user_id=user_id, submitted_at=datetime.now(timezone.utc), idempotency_key=idempotency_key,
    )
    return success(response)
