"""DTOs for the /api/v1/auth/* and /api/v1/me* contracts (EPIC-M1.145)."""

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


class SessionRequest(BaseModel):
    """Only consulted when establishing a brand-new session (no valid
    ``Authorization`` bearer session token on the request) -- see
    ``api/services/auth.py``. ``userId`` is verified by whichever
    ``CredentialVerifier`` this deployment configures (see
    ``app.auth_session``); the default, until a real identity provider is
    integrated, is self-asserted."""

    userId: str | None = None


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
