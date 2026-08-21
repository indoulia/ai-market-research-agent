"""GET /api/v1/feedback/history (EPIC-M3.10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db, require_bearer_subject
from ..envelope import cursor_paginated
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope
from ..schemas.feedback import FeedbackHistoryItem
from ..services.feedback import get_feedback_history

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("/history", response_model=CursorEnvelope[FeedbackHistoryItem])
def get_feedback_history_endpoint(
    db: Session = Depends(get_db),
    user_id: str = Depends(require_bearer_subject),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = get_feedback_history(db, user_id=user_id, cursor=cursor, page_size=pageSize)
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)
