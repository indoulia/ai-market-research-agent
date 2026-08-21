"""Service backing /api/v1/auth/session, /api/v1/auth/logout, /api/v1/me
and /api/v1/me/permissions (EPIC-M1.145).

``POST /auth/session`` does double duty as the contract's "establish/
refresh" endpoint: a request carrying a currently-valid session token
(``Authorization: Bearer ...``) refreshes (rotates) it; a request with no
such header establishes a brand-new session from the request body's
credential. This mirrors how mobile/web clients actually behave (silently
refresh while a session exists, fall back to a fresh login once it
doesn't) without needing two endpoints for it, matching the documented
single-endpoint contract.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.auth_session import (
    STATUS_VALID,
    SelfAssertedCredentialVerifier,
    create_session,
    get_session_status,
    refresh_session,
    revoke_session,
)

from ..deps import get_optional_bearer_subject
from ..errors import UnauthenticatedError, ValidationError
from ..request_context import get_request_id
from ..schemas.auth import DEFAULT_CAPABILITIES, PermissionsResponse, SessionRequest, SessionResponse, UserContext

_verifier = SelfAssertedCredentialVerifier()


def _to_response(auth_session) -> SessionResponse:
    return SessionResponse(
        sessionToken=auth_session.session_token, userId=auth_session.user_id,
        issuedAt=auth_session.issued_at, expiresAt=auth_session.expires_at,
    )


def establish_or_refresh_session(db: Session, request: SessionRequest, *, authorization: str | None) -> SessionResponse:
    existing_token = get_optional_bearer_subject(authorization)
    if existing_token:
        status, _ = get_session_status(db, existing_token, at=datetime.now(timezone.utc))
        if status == STATUS_VALID:
            # Only a currently-live session can be silently refreshed
            # (rotated to a new token with a fresh expiry). An expired
            # session is never silently renewed -- that would defeat the
            # point of expiry -- so it falls through to requiring a fresh
            # credential below, same as no session token at all.
            new_session = refresh_session(db, existing_token, at=datetime.now(timezone.utc))
            return _to_response(new_session)

    user_id = _verifier.verify(request.model_dump())
    if user_id is None:
        raise ValidationError("userId is required to establish a new session.", field_errors={"userId": "required"})

    new_session = create_session(db, user_id=user_id, issued_at=datetime.now(timezone.utc))
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
