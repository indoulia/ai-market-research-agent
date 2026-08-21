"""EPIC-M1.145: a real, server-managed session lifecycle for the API's
authentication/session boundary.

"Authentication mechanism remains configurable at deployment level"
(Rule) is implemented as a `CredentialVerifier` Protocol -- the same
provider-abstraction shape this platform already uses for market-data
providers (M1.90's `typing.Protocol` + concrete adapter pattern). The
only concrete verifier shipped here, `SelfAssertedCredentialVerifier`,
is an explicit placeholder: it trusts whatever `userId` the caller
presents, with no password/OAuth/SSO check at all, because this
platform has no user-credential store yet. A real deployment plugs in a
different `CredentialVerifier` (checking a password hash, an OAuth
token, an SSO assertion) without changing anything below this module or
the API contract in front of it.

Once a caller's identity is established (by whatever verifier), this
module owns the SESSION itself: a real, persisted, expiring, revocable,
rotatable token -- not a self-asserted bearer string. This is what
upgrades `api/deps.py::require_bearer_subject` from "any string is
accepted" (the honest placeholder M1.132/M1.141 documented) to actual
enforcement.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuthSession

SESSION_RULE_VERSION = "AUS-001"

DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60  # 8 hours


class CredentialVerifier(Protocol):
    def verify(self, credential: dict) -> str | None:
        """Returns the verified user_id, or None if the credential is invalid."""
        ...


class SelfAssertedCredentialVerifier:
    """Placeholder verifier: trusts a client-supplied `userId` outright.

    Not a security control -- see this module's docstring. Swap for a
    real verifier (password/OAuth/SSO) when this platform has one,
    without changing the session lifecycle below or the API contract.
    """

    def verify(self, credential: dict) -> str | None:
        user_id = credential.get("userId")
        return user_id if isinstance(user_id, str) and user_id.strip() else None


class InvalidCredentialError(ValueError):
    pass


class SessionNotFoundError(ValueError):
    pass


class SessionExpiredError(ValueError):
    pass


def _generate_token() -> str:
    return secrets.token_hex(32)


def create_session(
    session: Session, *, user_id: str, issued_at: datetime, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
) -> AuthSession:
    auth_session = AuthSession(
        session_token=_generate_token(),
        user_id=user_id,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(seconds=ttl_seconds),
        revoked_at=None,
        previous_session_id=None,
        session_rule_version=SESSION_RULE_VERSION,
    )
    session.add(auth_session)
    session.commit()
    session.refresh(auth_session)
    return auth_session


def _as_aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def get_active_session(session: Session, token: str, *, at: datetime) -> AuthSession | None:
    """Returns the session for `token` only if it is currently valid
    (exists, not revoked, not expired). Returns `None` for every other
    case -- callers that need to distinguish "expired" from "never
    existed"/"revoked" (AC: expired sessions get a deterministic error
    code) should use `get_session_status` instead."""
    auth_session = session.scalar(select(AuthSession).where(AuthSession.session_token == token))
    if auth_session is None:
        return None
    if auth_session.revoked_at is not None:
        return None
    if _as_aware_utc(auth_session.expires_at) <= at:
        return None
    return auth_session


STATUS_VALID = "VALID"
STATUS_NOT_FOUND = "NOT_FOUND"
STATUS_REVOKED = "REVOKED"
STATUS_EXPIRED = "EXPIRED"


def get_session_status(session: Session, token: str, *, at: datetime) -> tuple[str, AuthSession | None]:
    auth_session = session.scalar(select(AuthSession).where(AuthSession.session_token == token))
    if auth_session is None:
        return STATUS_NOT_FOUND, None
    if auth_session.revoked_at is not None:
        return STATUS_REVOKED, auth_session
    if _as_aware_utc(auth_session.expires_at) <= at:
        return STATUS_EXPIRED, auth_session
    return STATUS_VALID, auth_session


def refresh_session(
    session: Session, token: str, *, at: datetime, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
) -> AuthSession:
    """Rotates `token` for a fresh one with a new expiry, and revokes the
    old one -- a refreshed session is never just an expiry-extension of
    the same token (AC: "session expiry and refresh behavior are
    explicit"). Raises `SessionNotFoundError`/`SessionExpiredError` for
    a token that can't be refreshed instead of silently minting a
    session for an unauthenticated caller."""
    status, auth_session = get_session_status(session, token, at=at)
    if status in (STATUS_NOT_FOUND, STATUS_REVOKED):
        raise SessionNotFoundError(f"session token is invalid ({status.lower()})")
    if status == STATUS_EXPIRED:
        raise SessionExpiredError("session token has expired")

    auth_session.revoked_at = at
    session.add(auth_session)

    new_session = AuthSession(
        session_token=_generate_token(),
        user_id=auth_session.user_id,
        issued_at=at,
        expires_at=at + timedelta(seconds=ttl_seconds),
        revoked_at=None,
        previous_session_id=auth_session.id,
        session_rule_version=SESSION_RULE_VERSION,
    )
    session.add(new_session)
    session.commit()
    session.refresh(new_session)
    return new_session


def revoke_session(session: Session, token: str, *, at: datetime) -> bool:
    """Idempotent: revoking an already-revoked or never-existent token is
    not an error (AC: "logout invalidates session according to policy")
    -- returns whether a session was actually revoked by this call."""
    auth_session = session.scalar(select(AuthSession).where(AuthSession.session_token == token))
    if auth_session is None or auth_session.revoked_at is not None:
        return False
    auth_session.revoked_at = at
    session.add(auth_session)
    session.commit()
    return True
