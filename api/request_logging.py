"""Structured request-path observability for /api/v1 (EPIC-M1.132 gap
closed in the 2026-08-21 QA/integration audit -- previously no request-path
logging existed anywhere in api/ or app/).

Deliberately logs only operational metadata (request id, method, route,
status, duration, timestamp) -- never headers, bearer tokens, request/response
bodies, or any other value that could carry credentials or PII.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.settings import settings

logger = logging.getLogger("mra.api.request")

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"message": record.getMessage()}
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload)


def configure_request_logging() -> None:
    """Idempotent: safe to call every time `register_api` runs (e.g. once per
    test-created app instance) without installing duplicate handlers."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(settings.log_level)
    _CONFIGURED = True


def log_request(*, request_id: str, method: str, route: str, status_code: int, duration_ms: float) -> None:
    # migrations/env.py calls `logging.config.fileConfig(...)` (Alembic's default) on
    # every real `alembic upgrade`/`downgrade` call, which disables every *existing*
    # logger not explicitly listed in alembic.ini's [loggers] section -- including this
    # one, process-wide, for the rest of the run. Defensively re-enable on every call
    # rather than only at configure time, since the disabling can happen well after
    # `configure_request_logging()` already ran (e.g. a later test invoking Alembic).
    logger.disabled = False
    logger.info(
        "",
        extra={
            "fields": {
                "requestId": request_id,
                "method": method,
                "route": route,
                "status": status_code,
                "durationMs": round(duration_ms, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
