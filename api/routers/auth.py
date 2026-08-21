"""POST /api/v1/auth/session, POST /api/v1/auth/logout, GET /api/v1/me,
GET /api/v1/me/permissions (EPIC-M1.145)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.models import AuthSession

from ..deps import get_db, require_active_session
from ..envelope import success
from ..schemas.common import SuccessEnvelope
from ..schemas.auth import LogoutResponse, PermissionsResponse, SessionRequest, SessionResponse, UserContext
from ..services.auth import establish_or_refresh_session, get_permissions, get_user_context, logout

router = APIRouter(tags=["auth"])


@router.post("/auth/session", response_model=SuccessEnvelope[SessionResponse])
def post_auth_session(
    request: SessionRequest | None = None,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    body = request if request is not None else SessionRequest()
    return success(establish_or_refresh_session(db, body, authorization=authorization))


@router.post("/auth/logout", response_model=SuccessEnvelope[LogoutResponse])
def post_auth_logout(db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    revoked = logout(db, authorization=authorization)
    return success(LogoutResponse(revoked=revoked))


@router.get("/me", response_model=SuccessEnvelope[UserContext])
def get_me(auth_session: AuthSession = Depends(require_active_session)):
    return success(get_user_context(auth_session))


@router.get("/me/permissions", response_model=SuccessEnvelope[PermissionsResponse])
def get_me_permissions(auth_session: AuthSession = Depends(require_active_session)):
    return success(get_permissions(auth_session))
