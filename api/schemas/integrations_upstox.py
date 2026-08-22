"""DTOs for GET /api/v1/integrations/upstox/{authorize,status} (EPIC-
MARKSY-0001). `access_token`/`client_secret`/`code`/`state` never appear
in any of these -- status is derived purely from `UpstoxOAuthToken`'s
timestamps (see app/upstox_oauth.py)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UpstoxAuthorizeResponse(BaseModel):
    authorizationUrl: str
    state: str
    expiresAt: datetime


class UpstoxStatusResponse(BaseModel):
    connected: bool
    isExpired: bool
    obtainedAt: datetime | None
    expiresAt: datetime | None
    environment: str
