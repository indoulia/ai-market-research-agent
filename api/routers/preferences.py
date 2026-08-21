"""GET/PUT /api/v1/preferences (EPIC-M1.141)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import get_db, require_bearer_subject
from ..envelope import success
from ..schemas.common import SuccessEnvelope
from ..schemas.preferences import PreferencesDocument, PreferencesUpdateRequest
from ..services.preferences import get_preferences, update_preferences

router = APIRouter(tags=["preferences"])


@router.get("/preferences", response_model=SuccessEnvelope[PreferencesDocument])
def get_user_preferences(db: Session = Depends(get_db), user_id: str = Depends(require_bearer_subject)):
    return success(get_preferences(db, user_id, at=datetime.now(timezone.utc)))


@router.put("/preferences", response_model=SuccessEnvelope[PreferencesDocument])
def put_user_preferences(
    request: PreferencesUpdateRequest, db: Session = Depends(get_db), user_id: str = Depends(require_bearer_subject)
):
    return success(update_preferences(db, user_id, request, at=datetime.now(timezone.utc)))
