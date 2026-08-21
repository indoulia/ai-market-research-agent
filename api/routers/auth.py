"""POST /api/v1/auth/login, POST /api/v1/auth/refresh,
GET /api/v1/auth/session, POST /api/v1/auth/logout, GET /api/v1/me,
GET /api/v1/me/permissions (EPIC-M1.145, endpoint split to EPIC-M3.12's
login/refresh/session contract)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.models import AuthSession

from ..deps import get_db, require_active_session
from ..envelope import success
from ..schemas.common import SuccessEnvelope
from ..schemas.auth import LoginRequest, LogoutResponse, PermissionsResponse, SessionResponse, UserContext
from ..services.auth import get_permissions, get_user_context, login, logout, refresh

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=SuccessEnvelope[SessionResponse])
def post_auth_login(request: LoginRequest, db: Session = Depends(get_db)):
    return success(login(db, request))


@router.post("/auth/refresh", response_model=SuccessEnvelope[SessionResponse])
def post_auth_refresh(db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    return success(refresh(db, authorization=authorization))


@router.get("/auth/session", response_model=SuccessEnvelope[UserContext])
def get_auth_session(auth_session: AuthSession = Depends(require_active_session)):
    return success(get_user_context(auth_session))


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
