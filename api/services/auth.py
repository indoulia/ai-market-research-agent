"""Service backing /api/v1/auth/login, /api/v1/auth/refresh,
/api/v1/auth/session, /api/v1/auth/logout, /api/v1/me and
/api/v1/me/permissions.

EPIC-M1.145 shipped the session lifecycle (``app/auth_session.py``) behind
a single combined ``POST /auth/session`` "establish-or-refresh" endpoint.
EPIC-M3.12 defines the same lifecycle behind three explicit verbs instead
-- ``login`` (always establishes a brand-new session), ``refresh`` (always
rotates an existing live one) and ``GET session`` (reads the current one,
alongside ``GET /me``) -- so this module now exposes ``login``/``refresh``
as distinct functions rather than one that branches on whether a bearer
token happened to be present.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.auth_session import (
    STATUS_EXPIRED,
    STATUS_VALID,
    SelfAssertedCredentialVerifier,
    create_session,
    get_session_status,
    refresh_session,
    revoke_session,
)

from ..deps import SessionExpiredApiError, get_optional_bearer_subject
from ..errors import UnauthenticatedError, ValidationError
from ..request_context import get_request_id
from ..schemas.auth import DEFAULT_CAPABILITIES, LoginRequest, PermissionsResponse, SessionResponse, UserContext

_verifier = SelfAssertedCredentialVerifier()


def _to_response(auth_session) -> SessionResponse:
    return SessionResponse(
        sessionToken=auth_session.session_token, userId=auth_session.user_id,
        issuedAt=auth_session.issued_at, expiresAt=auth_session.expires_at,
    )


def login(db: Session, request: LoginRequest) -> SessionResponse:
    """``POST /auth/login`` -- always establishes a brand-new session from
    the caller's credential, regardless of any session token already on
    the request. Unlike M1.145's combined endpoint, login never silently
    refreshes an existing session -- that is `refresh`'s job."""
    user_id = _verifier.verify(request.model_dump())
    if user_id is None:
        raise ValidationError("userId is required to sign in.", field_errors={"userId": "required"})
    new_session = create_session(db, user_id=user_id, issued_at=datetime.now(timezone.utc))
    return _to_response(new_session)


def refresh(db: Session, *, authorization: str | None) -> SessionResponse:
    """``POST /auth/refresh`` -- rotates the caller's currently-live
    session token for a fresh one with a new expiry. A missing/unknown/
    revoked token raises the generic ``MRA_UNAUTHENTICATED`` (an attacker
    can't use the error to probe which tokens ever existed); an
    expired-but-otherwise-real token raises the deterministic
    ``MRA_SESSION_EXPIRED`` instead -- refreshing an already-expired
    session would defeat the point of expiry, so the caller must sign in
    again via `login`."""
    token = get_optional_bearer_subject(authorization)
    if not token:
        raise UnauthenticatedError()
    status, _ = get_session_status(db, token, at=datetime.now(timezone.utc))
    if status == STATUS_EXPIRED:
        raise SessionExpiredApiError()
    if status != STATUS_VALID:
        raise UnauthenticatedError()
    new_session = refresh_session(db, token, at=datetime.now(timezone.utc))
    return _to_response(new_session)


def logout(db: Session, *, authorization: str | None) -> bool:
    token = get_optional_bearer_subject(authorization)
    if not token:
        raise UnauthenticatedError()
    return revoke_session(db, token, at=datetime.now(timezone.utc))


def get_user_context(auth_session) -> UserContext:
    return UserContext(
        userId=auth_session.user_id,
        sessionIssuedAt=auth_session.issued_at,
        sessionExpiresAt=auth_session.expires_at,
        requestId=get_request_id(),
    )


def get_permissions(_auth_session) -> PermissionsResponse:
    return PermissionsResponse(capabilities=list(DEFAULT_CAPABILITIES))
