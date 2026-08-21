"""DTOs for the /api/v1/auth/* and /api/v1/me* contracts (EPIC-M1.145,
endpoint split to the EPIC-M3.12 `login`/`refresh`/`session` contract)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

# The full set of capabilities any authenticated caller currently has.
# This platform has no per-user roles/permissions system yet -- every
# authenticated user gets the same flat set. Real RBAC is a future EPIC;
# this is the honest current state, not a placeholder claiming more than
# it grants.
DEFAULT_CAPABILITIES = (
    "VIEW_RECOMMENDATIONS",
    "VIEW_DISCOVERIES",
    "VIEW_MARKET_DATA",
    "SUBMIT_FEEDBACK",
    "MANAGE_PREFERENCES",
)


class LoginRequest(BaseModel):
    """Body for ``POST /api/v1/auth/login`` (EPIC-M3.12). ``userId`` is
    verified by whichever ``CredentialVerifier`` this deployment configures
    (see ``app.auth_session``); the default, until a real identity provider
    is integrated, is self-asserted."""

    userId: str


class SessionResponse(BaseModel):
    sessionToken: str
    userId: str
    issuedAt: datetime
    expiresAt: datetime


class LogoutResponse(BaseModel):
    revoked: bool


class UserContext(BaseModel):
    userId: str
    sessionIssuedAt: datetime
    sessionExpiresAt: datetime
    requestId: str


class PermissionsResponse(BaseModel):
    capabilities: list[str]
