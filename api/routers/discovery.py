"""GET /api/v1/discoveries (EPIC-M1.139) and GET /api/v1/discovery/*
(EPIC-M3.6 discovery intelligence)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models import AuthSession

from ..deps import get_db, get_optional_active_session
from ..envelope import cursor_paginated, success
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope, SuccessEnvelope
from ..schemas.discovery import DiscoveryCandidate, DiscoveryHistoryPoint, DiscoveryItem, DiscoverySummary
from ..services.discovery import DiscoveryQuery, list_discoveries
from ..services.discovery_intelligence import (
    DEFAULT_HISTORY_DAYS,
    MAX_HISTORY_DAYS,
    CandidateQuery,
    HistoryQuery,
    get_discovery_history,
    get_discovery_summary,
    list_discovery_candidates,
)

router = APIRouter(tags=["discoveries"])


@router.get("/discoveries", response_model=CursorEnvelope[DiscoveryItem])
def get_discoveries(
    db: Session = Depends(get_db),
    market: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    marketCapBucket: str | None = Query(default=None),
    liquidity: str | None = Query(default=None, description="LOW|NORMAL|HIGH"),
    minScore: Decimal | None = Query(default=None),
    sort: str = Query(default="discoveredAt", description="discoveredAt|score"),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = list_discoveries(
        db,
        DiscoveryQuery(
            market=market, sector=sector, industry=industry, market_cap_bucket=marketCapBucket,
            liquidity=liquidity, min_score=minScore, sort=sort, direction=direction,
            page_size=pageSize, cursor=cursor,
        ),
    )
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)


@router.get("/discovery/summary", response_model=SuccessEnvelope[DiscoverySummary])
def get_discovery_summary_endpoint(db: Session = Depends(get_db)):
    return success(get_discovery_summary(db))


@router.get("/discovery/history", response_model=SuccessEnvelope[list[DiscoveryHistoryPoint]])
def get_discovery_history_endpoint(
    db: Session = Depends(get_db),
    days: int = Query(default=DEFAULT_HISTORY_DAYS, ge=1, le=MAX_HISTORY_DAYS, description="Timeline length, in scan days"),
):
    return success(get_discovery_history(db, HistoryQuery(days=days)))


@router.get("/discovery/candidates", response_model=CursorEnvelope[DiscoveryCandidate])
def get_discovery_candidates(
    db: Session = Depends(get_db),
    market: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    marketCap: str | None = Query(
        default=None,
        description="LARGE_CAP|MID_CAP|SMALL_CAP|UNCLASSIFIED (the \"size\" filter -- same bucket vocabulary as M1.139's `marketCapBucket`, per EPIC-M3.6's own `marketCap` field name)",
    ),
    discoveryBasis: str | None = Query(default=None, description="CHATGPT|DAILY_UNIVERSE_SCAN|WATCHLIST"),
    discoveredFrom: date | None = Query(default=None, alias="from", description="Inclusive discoveredAt lower bound (date)"),
    discoveredTo: date | None = Query(default=None, alias="to", description="Inclusive discoveredAt upper bound (date)"),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
    auth_session: AuthSession | None = Depends(get_optional_active_session),
):
    page = list_discovery_candidates(
        db,
        CandidateQuery(
            market=market, sector=sector, industry=industry, market_cap_bucket=marketCap,
            discovery_basis=discoveryBasis, discovered_from=discoveredFrom, discovered_to=discoveredTo,
            page_size=pageSize, cursor=cursor,
        ),
    )
    items = page.items
    if auth_session is None:
        # Suppression reason is internal/authorized detail (EPIC-M3.6 UI
        # Scope) -- an unauthenticated caller sees the lifecycle stage
        # ("SUPPRESSED") but not the underlying reason text.
        items = [item.model_copy(update={"suppressionReason": None}) for item in items]
    return cursor_paginated(items, page_size=pageSize, next_cursor=page.next_cursor)
