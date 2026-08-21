"""GET /api/v1/discoveries (EPIC-M1.139)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import cursor_paginated
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope
from ..schemas.discovery import DiscoveryItem
from ..services.discovery import DiscoveryQuery, list_discoveries

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
