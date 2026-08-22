"""EPIC-MARKSY-0001: Upstox OAuth authorization-code flow and access-token
lifecycle.

**Repository OAuth due diligence (S1), recorded here rather than guessed:**
this backend runs as a single FastAPI process on port 8000 (`Dockerfile`'s
`CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`,
mirrored by `docker-compose.yml`'s `api` service `ports: ["8000:8000"]`).
Every contract route is mounted under `API_PREFIX` (`api/versioning.py`,
currently `/api/v1`). No OAuth callback route existed anywhere in this
repository before this EPIC (confirmed by grep across `api/` and `app/`
for "callback"/"oauth"/"redirect_uri"). The existing `/api/v1/auth/*`
routes (`api/routers/auth.py`, EPIC-M1.145) are Marksy's own end-user
session login and are unrelated to this broker-level OAuth connection.

Upstox's authorization-code flow therefore has its real, repository-
verified browser-visible callback at:

    http://localhost:8000/api/v1/integrations/upstox/callback   (GET)

served directly by the `api` container/process already exposed on the
host at port 8000 -- no extra Docker Compose/Kubernetes port needs adding,
since this reuses the API's existing exposed port and prefix. This exact
value is what `UPSTOX_REDIRECT_URI` must be set to, and must also be the
literal redirect URI registered in the Upstox developer app (Upstox
rejects a mismatch). See `.env.example` for the documented variable.

**Token lifecycle note (S3), an explicit assumption, not repository
evidence:** Upstox's OAuth v2 token endpoint does not return a
`refresh_token`/`expires_in` pair -- Upstox's documented behavior is that
every issued access token expires at a fixed daily cutover (3:30 AM IST)
regardless of issue time, and the only way to obtain a new one is to
repeat the full authorization-code flow. This module models expiry that
way (`_next_daily_cutover`) and never fabricates a refresh-token grant
Upstox doesn't support. This assumption should be confirmed against a
real token response during the EPIC's controlled real-provider
validation step (see completion report) -- if Upstox's actual response
ever includes `expires_in`, prefer that over the assumed cutover.
"""

from __future__ import annotations

import secrets
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import UpstoxOAuthState, UpstoxOAuthToken
from .settings import settings

UPSTOX_OAUTH_VERSION = "UOA-001"

AUTHORIZATION_DIALOG_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"

STATE_TTL_SECONDS = 10 * 60

_IST = ZoneInfo("Asia/Kolkata")
_DAILY_CUTOVER_IST = time(3, 30)


class UpstoxOAuthError(RuntimeError):
    """Raised for a provider-side OAuth failure (bad code, provider HTTP
    error, malformed token response) -- never allowed to leak a bare
    `httpx`/parsing exception into router/service code."""


class UpstoxNotConfiguredError(RuntimeError):
    """Raised when client id/secret/redirect URI are not set. Checked
    lazily at the point the OAuth flow is actually invoked, not at process
    startup, since a deployment running MARKET_DATA_PROVIDER=yahoo never
    needs Upstox configured at all."""


def require_oauth_config() -> tuple[str, str, str]:
    client_id, client_secret, redirect_uri = (
        settings.upstox_client_id,
        settings.upstox_client_secret,
        settings.upstox_redirect_uri,
    )
    missing = [
        name
        for name, value in (
            ("UPSTOX_CLIENT_ID", client_id),
            ("UPSTOX_CLIENT_SECRET", client_secret),
            ("UPSTOX_REDIRECT_URI", redirect_uri),
        )
        if not value
    ]
    if missing:
        raise UpstoxNotConfiguredError(f"missing required configuration: {', '.join(missing)}")
    return client_id, client_secret, redirect_uri


def _generate_state() -> str:
    return secrets.token_urlsafe(32)


def create_oauth_state(session: Session, *, issued_at: datetime) -> UpstoxOAuthState:
    oauth_state = UpstoxOAuthState(
        state=_generate_state(),
        expires_at=issued_at + timedelta(seconds=STATE_TTL_SECONDS),
        consumed_at=None,
    )
    session.add(oauth_state)
    session.commit()
    session.refresh(oauth_state)
    return oauth_state


def build_authorization_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state}
    )
    return f"{AUTHORIZATION_DIALOG_URL}?{query}"


def consume_oauth_state(session: Session, state: str, *, at: datetime) -> bool:
    """One-time-use CSRF check (S2 AC: "no authorization code/token
    leakage" starts with "the callback can't be replayed/forged"). Returns
    False -- never raises -- for an unknown, already-consumed, or expired
    state, so the callback handler can return a uniform, generic failure
    without distinguishing *why* to a caller that doesn't control that
    input (the caller is Upstox's redirect, but the browser is the
    end-user's)."""
    oauth_state = session.scalar(select(UpstoxOAuthState).where(UpstoxOAuthState.state == state))
    if oauth_state is None or oauth_state.consumed_at is not None:
        return False
    expires_at = oauth_state.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= at:
        return False
    oauth_state.consumed_at = at
    session.add(oauth_state)
    session.commit()
    return True


def exchange_authorization_code(
    code: str, *, client_id: str, client_secret: str, redirect_uri: str, timeout: float = 30.0
) -> dict:
    """POSTs the authorization code to Upstox's token endpoint. Never logs
    `code`/`client_secret`/the response body (S2/security rules) --
    callers must not either."""
    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise UpstoxOAuthError("Upstox token exchange request failed") from exc

    if response.status_code >= 400:
        raise UpstoxOAuthError(f"Upstox token exchange rejected the authorization code (HTTP {response.status_code})")

    try:
        payload = response.json()
    except ValueError as exc:
        raise UpstoxOAuthError("Upstox token exchange returned a non-JSON response") from exc

    access_token = payload.get("access_token")
    if not access_token:
        raise UpstoxOAuthError("Upstox token exchange response is missing access_token")
    return payload


def _next_daily_cutover(after: datetime) -> datetime:
    local = after.astimezone(_IST)
    cutover_today = local.replace(
        hour=_DAILY_CUTOVER_IST.hour, minute=_DAILY_CUTOVER_IST.minute, second=0, microsecond=0
    )
    cutover = cutover_today if cutover_today > local else cutover_today + timedelta(days=1)
    return cutover.astimezone(timezone.utc)


def store_token(session: Session, token_response: dict, *, obtained_at: datetime) -> UpstoxOAuthToken:
    expires_in = token_response.get("expires_in")
    expires_at = obtained_at + timedelta(seconds=int(expires_in)) if expires_in else _next_daily_cutover(obtained_at)
    token = UpstoxOAuthToken(
        access_token=token_response["access_token"],
        token_type=token_response.get("token_type") or "Bearer",
        upstox_user_id=token_response.get("user_id"),
        obtained_at=obtained_at,
        expires_at=expires_at,
        revoked_at=None,
    )
    session.add(token)
    session.commit()
    session.refresh(token)
    return token


def get_latest_token(session: Session) -> UpstoxOAuthToken | None:
    return session.scalar(
        select(UpstoxOAuthToken)
        .where(UpstoxOAuthToken.revoked_at.is_(None))
        .order_by(UpstoxOAuthToken.obtained_at.desc())
        .limit(1)
    )


def _as_aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def is_token_valid(token: UpstoxOAuthToken, *, at: datetime) -> bool:
    return token.revoked_at is None and _as_aware_utc(token.expires_at) > at


def resolve_access_token(session: Session, *, at: datetime | None = None) -> str | None:
    """Single source of truth for "what access token should a market-data
    call use right now" (S4/S8): a currently-valid OAuth-obtained token
    takes priority; `UPSTOX_ACCESS_TOKEN` (a manually pasted token, e.g.
    for CI or before OAuth is wired up in a given environment) is the
    fallback. Returns `None` -- never raises -- when neither is available,
    so callers can produce their own clear "not configured" error."""
    at = at or datetime.now(timezone.utc)
    token = get_latest_token(session)
    if token is not None and is_token_valid(token, at=at):
        return token.access_token
    return settings.upstox_access_token or None
