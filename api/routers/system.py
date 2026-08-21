"""GET /api/v1/system/{health,providers,data-freshness,events} (EPIC-M3.11).

Read-only operational surface -- no route here ever accepts a body or
mutates state, satisfying the EPIC's own "health state is read-only to
normal users" AC structurally. No provider credential/config is ever
serialized: every response field comes from `app.provider_quality`'s
already-aggregated `DataFetchAttempt` metrics, never from a live provider
instance's own configuration.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import cursor_paginated, success
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope, SuccessEnvelope
from ..schemas.system import DataFreshnessItem, ProviderStatus, SystemEventItem, SystemHealthResponse
from ..services.system_health import get_data_freshness, get_provider_status, get_system_events, get_system_health

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=SuccessEnvelope[SystemHealthResponse])
def get_health(db: Session = Depends(get_db)):
    return success(get_system_health(db, computed_at=datetime.now(timezone.utc)))


@router.get("/providers", response_model=SuccessEnvelope[list[ProviderStatus]])
def get_providers(db: Session = Depends(get_db)):
    return success(get_provider_status(db, computed_at=datetime.now(timezone.utc)))


@router.get("/data-freshness", response_model=SuccessEnvelope[list[DataFreshnessItem]])
def get_data_freshness_endpoint(db: Session = Depends(get_db)):
    return success(get_data_freshness(db, computed_at=datetime.now(timezone.utc)))


@router.get("/events", response_model=CursorEnvelope[SystemEventItem])
def get_events(
    db: Session = Depends(get_db),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = get_system_events(db, page_size=pageSize, cursor=cursor)
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)
