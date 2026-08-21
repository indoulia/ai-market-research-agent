"""Builders for the canonical success/error response envelopes (EPIC-M1.132)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .errors import ApiError
from .request_context import get_request_id


def _meta(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = {"requestId": get_request_id(), "timestamp": datetime.now(timezone.utc)}
    if extra:
        meta.update(extra)
    return meta


def success(data: Any) -> dict[str, Any]:
    return {"data": data, "meta": _meta()}


def paginated(items: list[Any], *, page: int, page_size: int, total_items: int) -> dict[str, Any]:
    total_pages = (total_items + page_size - 1) // page_size if page_size else 0
    return {"data": items, "meta": _meta({"page": page, "pageSize": page_size, "totalItems": total_items, "totalPages": total_pages})}


def error_body(exc: ApiError) -> dict[str, Any]:
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "retryable": exc.retryable,
        },
        "meta": _meta(),
    }
