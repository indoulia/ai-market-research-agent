"""GET /api/v1/recommendations (EPIC-M1.135)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import cursor_paginated
from ..pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..schemas.common import CursorEnvelope
from ..schemas.recommendations import RecommendationSummary
from ..services.recommendations import RecommendationQuery, list_recommendations

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations", response_model=CursorEnvelope[RecommendationSummary])
def get_recommendations(
    db: Session = Depends(get_db),
    horizon: int | None = Query(default=None, description="1|3|5|7 trading-day horizon"),
    market: str | None = Query(default=None, description="Exchange, e.g. nse"),
    sector: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    marketCapBucket: str | None = Query(default=None, description="LARGE_CAP|MID_CAP|SMALL_CAP|UNCLASSIFIED"),
    minScore: Decimal | None = Query(default=None),
    minTrust: Decimal | None = Query(default=None),
    sort: str = Query(default="score", description="score|trust|upside|confidence|updatedAt"),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
):
    page = list_recommendations(
        db,
        RecommendationQuery(
            horizon=horizon,
            market=market,
            sector=sector,
            industry=industry,
            market_cap_bucket=marketCapBucket,
            min_score=minScore,
            min_trust=minTrust,
            sort=sort,
            direction=direction,
            page_size=pageSize,
            cursor=cursor,
        ),
    )
    return cursor_paginated(page.items, page_size=pageSize, next_cursor=page.next_cursor)
