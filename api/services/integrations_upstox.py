"""Service layer for GET /api/v1/integrations/upstox/{authorize,status}
and the Upstox OAuth callback (EPIC-MARKSY-0001)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.upstox_oauth import (
    UpstoxNotConfiguredError,
    UpstoxOAuthError,
    build_authorization_url,
    create_oauth_state,
    exchange_authorization_code,
    get_latest_token,
    is_token_valid,
    require_oauth_config,
    store_token,
)
from app.settings import settings

from ..errors import ApiError


class UpstoxNotConfiguredApiError(ApiError):
    def __init__(self) -> None:
        super().__init__(
            "MRA_UPSTOX_NOT_CONFIGURED",
            "Upstox OAuth is not configured (UPSTOX_CLIENT_ID/UPSTOX_CLIENT_SECRET/UPSTOX_REDIRECT_URI).",
            http_status=409,
            retryable=False,
        )


class UpstoxOAuthFailedApiError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__("MRA_UPSTOX_OAUTH_FAILED", message, http_status=502, retryable=True)


def build_authorize_response(db: Session, *, at: datetime) -> dict:
    try:
        client_id, _client_secret, redirect_uri = require_oauth_config()
    except UpstoxNotConfiguredError as exc:
        raise UpstoxNotConfiguredApiError() from exc

    oauth_state = create_oauth_state(db, issued_at=at)
    authorization_url = build_authorization_url(client_id=client_id, redirect_uri=redirect_uri, state=oauth_state.state)
    return {"authorizationUrl": authorization_url, "state": oauth_state.state, "expiresAt": oauth_state.expires_at}


def complete_oauth_callback(db: Session, *, code: str, at: datetime) -> None:
    """Raises `UpstoxOAuthFailedApiError`/`UpstoxNotConfiguredApiError` on
    any failure -- the router translates these into the plain HTML landing
    page a browser (not an API client) is looking at, never a JSON error
    body (S2: this endpoint is reached only via Upstox's own redirect)."""
    try:
        client_id, client_secret, redirect_uri = require_oauth_config()
    except UpstoxNotConfiguredError as exc:
        raise UpstoxNotConfiguredApiError() from exc

    try:
        token_response = exchange_authorization_code(
            code, client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri
        )
    except UpstoxOAuthError as exc:
        raise UpstoxOAuthFailedApiError(str(exc)) from exc

    store_token(db, token_response, obtained_at=at)


def get_status(db: Session, *, at: datetime) -> dict:
    token = get_latest_token(db)
    if token is None:
        return {"connected": False, "isExpired": False, "obtainedAt": None, "expiresAt": None, "environment": settings.upstox_environment}
    valid = is_token_valid(token, at=at)
    return {
        "connected": valid,
        "isExpired": not valid,
        "obtainedAt": token.obtained_at,
        "expiresAt": token.expires_at,
        "environment": settings.upstox_environment,
    }
