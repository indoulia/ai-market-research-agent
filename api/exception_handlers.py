"""Registers exception -> canonical error envelope mapping (EPIC-M1.132)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from .envelope import error_body
from .errors import ApiError, InternalError, ValidationError

_STATUS_TO_CODE = {
    401: "MRA_UNAUTHENTICATED",
    403: "MRA_FORBIDDEN",
    404: "MRA_NOT_FOUND",
    405: "MRA_METHOD_NOT_ALLOWED",
    429: "MRA_RATE_LIMITED",
}


def _json_response(exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=jsonable_encoder(error_body(exc)))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return _json_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        field_errors = {".".join(str(p) for p in err["loc"]): err["msg"] for err in exc.errors()}
        return _json_response(ValidationError("Request validation failed.", field_errors=field_errors))

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, "MRA_ERROR")
        return _json_response(
            ApiError(code, str(exc.detail), http_status=exc.status_code, retryable=exc.status_code >= 500)
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return _json_response(InternalError())
