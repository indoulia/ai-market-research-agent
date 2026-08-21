"""Per-request correlation id (EPIC-M1.132).

The request id is generated (or propagated from an inbound
``X-Request-Id`` header) by ``RequestContextMiddleware`` and made
available to route handlers without threading it through every function
signature.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-Id"

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    value = _request_id.get()
    return value or new_request_id()
