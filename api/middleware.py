"""Cross-cutting request/response processing for /api/v1 (EPIC-M1.132)."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .envelope import error_body
from .errors import ApiError, RateLimitedError
from .rate_limit import client_key, default_limiter
from .request_context import REQUEST_ID_HEADER, new_request_id, set_request_id
from .versioning import API_PREFIX

logger = logging.getLogger(__name__)

# EPIC-M3.13 — API Scope: "response-size monitoring". A response body this
# large for a single /api/v1 call means a summary/list endpoint is leaking
# unbounded/historical detail rather than a paginated, bounded payload; log
# it so it shows up in ops monitoring instead of silently shipping a slow,
# oversized response to a mobile client.
LARGE_RESPONSE_BYTES = 250_000


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates the correlation id and enforces the rate limit
    for every ``/api/v1`` request. Non-API routes (legacy ``/health`` etc.)
    pass through untouched.

    The rate-limit rejection is turned into an envelope response here,
    directly, rather than by re-raising for a global exception handler --
    exceptions raised by a ``BaseHTTPMiddleware`` sit outside the
    ``ExceptionMiddleware`` layer that FastAPI's ``@app.exception_handler``
    hooks into, so relying on that global handler here would silently
    degrade to a bare 500 instead of the canonical MRA_RATE_LIMITED envelope.
    """

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(API_PREFIX):
            return await call_next(request)

        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        set_request_id(request_id)

        try:
            default_limiter.check(client_key(request.client.host if request.client else None, None))
        except ApiError as exc:
            response = JSONResponse(status_code=exc.http_status, content=jsonable_error(exc))
            response.headers[REQUEST_ID_HEADER] = request_id
            if isinstance(exc, RateLimitedError):
                response.headers["Retry-After"] = str(exc.retry_after_seconds)
            return response

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        response.headers[REQUEST_ID_HEADER] = request_id
        # EPIC-M3.13 — API Scope: "Server timing/correlation metadata".
        # Correlation is X-Request-Id (above); this is the timing half —
        # a standard, client-parseable header (not just a server log line)
        # so a slow /api/v1 call is diagnosable from the response alone.
        response.headers["Server-Timing"] = f"total;dur={duration_ms:.1f}"

        content_length = response.headers.get("content-length")
        if content_length is not None and int(content_length) > LARGE_RESPONSE_BYTES:
            logger.warning(
                "Oversized /api/v1 response: %s %s returned %s bytes (requestId=%s)",
                request.method,
                request.url.path,
                content_length,
                request_id,
            )
        return response


def jsonable_error(exc: ApiError) -> dict:
    body = error_body(exc)
    body["meta"]["timestamp"] = body["meta"]["timestamp"].isoformat()
    return body
