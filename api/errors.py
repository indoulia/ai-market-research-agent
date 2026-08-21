"""Canonical error vocabulary and exception -> envelope mapping (EPIC-M1.132).

Every error the API returns uses an ``MRA_*`` code so Flutter can branch on
a stable string instead of parsing human-readable messages or HTTP status
alone. New codes should be added here, never invented ad hoc in a router.
"""

from __future__ import annotations

from fastapi import status


class ApiError(Exception):
    """Raised by routers/services to produce a canonical error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = status.HTTP_400_BAD_REQUEST,
        details: dict | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}
        self.retryable = retryable


class NotFoundError(ApiError):
    def __init__(self, resource: str, identifier: str, *, code: str = "MRA_NOT_FOUND") -> None:
        super().__init__(
            code,
            f"{resource} '{identifier}' was not found.",
            http_status=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "identifier": identifier},
            retryable=False,
        )


class ValidationError(ApiError):
    def __init__(self, message: str, *, field_errors: dict | None = None) -> None:
        super().__init__(
            "MRA_VALIDATION_FAILED",
            message,
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"fieldErrors": field_errors or {}},
            retryable=False,
        )


class UnauthenticatedError(ApiError):
    def __init__(self, message: str = "Authentication is required.") -> None:
        super().__init__(
            "MRA_UNAUTHENTICATED",
            message,
            http_status=status.HTTP_401_UNAUTHORIZED,
            retryable=False,
        )


class ForbiddenError(ApiError):
    def __init__(self, message: str = "You do not have access to this resource.") -> None:
        super().__init__(
            "MRA_FORBIDDEN",
            message,
            http_status=status.HTTP_403_FORBIDDEN,
            retryable=False,
        )


class RateLimitedError(ApiError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "MRA_RATE_LIMITED",
            "Too many requests. Please retry later.",
            http_status=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retryAfterSeconds": retry_after_seconds},
            retryable=True,
        )
        self.retry_after_seconds = retry_after_seconds


class ConflictError(ApiError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(code, message, http_status=status.HTTP_409_CONFLICT, details=details, retryable=False)


class InternalError(ApiError):
    def __init__(self, message: str = "An unexpected error occurred.") -> None:
        super().__init__(
            "MRA_INTERNAL",
            message,
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            retryable=True,
        )
