"""Shared FastAPI dependencies for the /api/v1 layer (EPIC-M1.132)."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Header
from sqlalchemy.orm import Session

from app.db import SessionLocal

from .errors import UnauthenticatedError


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_optional_bearer_subject(authorization: str | None = Header(default=None)) -> str | None:
    """Best-effort caller identity for rate-limiting/observability.

    This is NOT authentication/authorization enforcement -- that boundary is
    owned by EPIC-M1.145 (Auth/Session API). Endpoints that must actually
    require an authenticated user use ``require_bearer_subject`` below (or,
    once M1.145 lands, its real session-validated equivalent). Today this
    only extracts the raw bearer token string as an opaque rate-limit/logging
    key; it does not verify signatures, expiry, or scope.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return token or None


def require_bearer_subject(subject: str | None = Header(default=None, alias="Authorization")) -> str:
    resolved = get_optional_bearer_subject(subject)
    if not resolved:
        raise UnauthenticatedError()
    return resolved
