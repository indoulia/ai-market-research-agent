"""Shared FastAPI dependencies for the /api/v1 layer (EPIC-M1.132, session
enforcement added by EPIC-M1.145)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import Depends, Header
from sqlalchemy.orm import Session as OrmSession

from app.auth_session import STATUS_EXPIRED, STATUS_VALID, get_session_status
from app.db import SessionLocal
from app.models import AuthSession

from .errors import ApiError, UnauthenticatedError


def get_db() -> Iterator[OrmSession]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_optional_bearer_subject(authorization: str | None = Header(default=None)) -> str | None:
    """Best-effort caller identity for rate-limiting/observability only.

    Extracts the raw bearer token string without validating it against
    anything -- used purely as an opaque rate-limit/logging key. Endpoints
    that must actually require an authenticated caller use
    ``require_active_session``/``require_bearer_subject`` below instead,
    which validate against a real EPIC-M1.145 session.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return token or None


class SessionExpiredApiError(ApiError):
    def __init__(self) -> None:
        super().__init__(
            "MRA_SESSION_EXPIRED",
            "Your session has expired. Please sign in again.",
            http_status=401,
            retryable=False,
        )


def require_active_session(
    authorization: str | None = Header(default=None), db: OrmSession = Depends(get_db)
) -> AuthSession:
    """Real EPIC-M1.145 session enforcement: the bearer token must be a
    live, non-revoked, non-expired ``AuthSession`` token. Raises
    ``MRA_SESSION_EXPIRED`` (deterministic, per AC) for a token that was
    once valid but has since expired, and the generic ``MRA_UNAUTHENTICATED``
    for anything else invalid (missing header, unknown token, revoked
    token) -- deliberately not distinguishing those from each other so an
    invalid token can't be used to probe which tokens ever existed."""
    token = get_optional_bearer_subject(authorization)
    if not token:
        raise UnauthenticatedError()
    status, auth_session = get_session_status(db, token, at=datetime.now(timezone.utc))
    if status == STATUS_VALID:
        return auth_session
    if status == STATUS_EXPIRED:
        raise SessionExpiredApiError()
    raise UnauthenticatedError()


def require_bearer_subject(auth_session: AuthSession = Depends(require_active_session)) -> str:
    return auth_session.user_id
