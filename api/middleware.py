"""Cross-cutting request/response processing for /api/v1 (EPIC-M1.132)."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .envelope import error_body
from .errors import ApiError, RateLimitedError
from .rate_limit import client_key, default_limiter
from .request_context import REQUEST_ID_HEADER, new_request_id, set_request_id
from .request_logging import log_request
from .versioning import API_PREFIX


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
        started_at = time.monotonic()

        try:
            default_limiter.check(client_key(request.client.host if request.client else None, None))
        except ApiError as exc:
            response = JSONResponse(status_code=exc.http_status, content=jsonable_error(exc))
            response.headers[REQUEST_ID_HEADER] = request_id
            if isinstance(exc, RateLimitedError):
                response.headers["Retry-After"] = str(exc.retry_after_seconds)
            self._log(request, request_id, response.status_code, started_at)
            return response

        response: Response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        self._log(request, request_id, response.status_code, started_at)
        return response

    @staticmethod
    def _log(request: Request, request_id: str, status_code: int, started_at: float) -> None:
        log_request(
            request_id=request_id,
            method=request.method,
            route=request.url.path,
            status_code=status_code,
            duration_ms=(time.monotonic() - started_at) * 1000,
        )


def jsonable_error(exc: ApiError) -> dict:
    body = error_body(exc)
    body["meta"]["timestamp"] = body["meta"]["timestamp"].isoformat()
    return body
