"""GET /api/v1/integrations/upstox/{authorize,callback,status} (EPIC-
MARKSY-0001).

`authorize`/`status` are normal JSON contract endpoints behind this
platform's usual session auth. `callback` is different in kind: it is
reached only by the end-user's browser being redirected by Upstox after
approval, never by the Flutter app calling it as an API -- there is no
Marksy bearer token on that request, and the response is a small HTML
landing page (per app.upstox_oauth's module docstring: the exact
repository-verified callback route/port), not a JSON envelope.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.upstox_oauth import consume_oauth_state

from ..deps import get_db, require_active_session
from ..envelope import success
from ..schemas.common import SuccessEnvelope
from ..schemas.integrations_upstox import UpstoxAuthorizeResponse, UpstoxStatusResponse
from ..services.integrations_upstox import (
    UpstoxNotConfiguredApiError,
    UpstoxOAuthFailedApiError,
    build_authorize_response,
    complete_oauth_callback,
    get_status,
)

router = APIRouter(prefix="/integrations/upstox", tags=["integrations"])

_LANDING_PAGE = """<!doctype html><html><head><title>Upstox connection</title></head>
<body style="font-family:sans-serif;text-align:center;margin-top:4rem">
<h1>{heading}</h1><p>{detail}</p><p>You may close this tab and return to Marksy.</p>
</body></html>"""


@router.get("/authorize", response_model=SuccessEnvelope[UpstoxAuthorizeResponse])
def get_authorize(db: Session = Depends(get_db), _auth_session=Depends(require_active_session)):
    return success(build_authorize_response(db, at=datetime.now(timezone.utc)))


@router.get("/callback", response_class=HTMLResponse, include_in_schema=False)
def get_callback(
    db: Session = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    now = datetime.now(timezone.utc)
    if error:
        return HTMLResponse(_LANDING_PAGE.format(heading="Upstox connection declined", detail=error), status_code=400)
    if not code or not state or not consume_oauth_state(db, state, at=now):
        return HTMLResponse(
            _LANDING_PAGE.format(heading="Upstox connection failed", detail="This login link is invalid or has expired."),
            status_code=400,
        )
    try:
        complete_oauth_callback(db, code=code, at=now)
    except (UpstoxNotConfiguredApiError, UpstoxOAuthFailedApiError) as exc:
        return HTMLResponse(_LANDING_PAGE.format(heading="Upstox connection failed", detail=exc.message), status_code=502)
    return HTMLResponse(_LANDING_PAGE.format(heading="Upstox connected", detail="Marksy can now access your Upstox market data."))


@router.get("/status", response_model=SuccessEnvelope[UpstoxStatusResponse])
def get_status_endpoint(db: Session = Depends(get_db), _auth_session=Depends(require_active_session)):
    return success(get_status(db, at=datetime.now(timezone.utc)))
