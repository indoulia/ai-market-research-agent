"""GET /api/v1/opportunities (EPIC-M3.3)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ..envelope import success
from ..pagination import PageParams
from ..schemas.common import SuccessEnvelope
from ..schemas.opportunities import OpportunityFilters, OpportunityListResponse
from ..services.opportunities import DEFAULT_SORT, OpportunityQuery, list_opportunities

router = APIRouter(tags=["opportunities"])


@router.get("/opportunities", response_model=SuccessEnvelope[OpportunityListResponse])
def get_opportunities(
    db: Session = Depends(get_db),
    page_params: PageParams = Depends(),
    market: str | None = Query(default=None, description="Exchange, e.g. nse"),
    horizon: int | None = Query(default=None, description="1|3|5|7 trading-day horizon"),
    sector: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    marketCap: str | None = Query(default=None, description="LARGE_CAP|MID_CAP|SMALL_CAP|UNCLASSIFIED"),
    minTrust: Decimal | None = Query(default=None),
    minScore: Decimal | None = Query(default=None),
    minUpside: Decimal | None = Query(default=None),
    liquidityBucket: str | None = Query(default=None, description="HIGH|NORMAL|LOW|UNCLASSIFIED"),
    status: str | None = Query(default=None, description="ISSUED|AWAITING_HORIZON (defaults to both -- the open/live feed)"),
    search: str | None = Query(default=None, description="Substring match on symbol or company name"),
    sort: str = Query(default=DEFAULT_SORT, description="trust|score|upside|probability|freshness|ranking, '-' prefix for descending"),
):
    page = list_opportunities(
        db,
        OpportunityQuery(
            market=market,
            horizon=horizon,
            sector=sector,
            industry=industry,
            market_cap_bucket=marketCap,
            min_trust=minTrust,
            min_score=minScore,
            min_upside=minUpside,
            liquidity_bucket=liquidityBucket,
            status=status,
            search=search,
            sort=sort,
            page=page_params.page,
            page_size=page_params.page_size,
        ),
    )
    return success(
        OpportunityListResponse(
            items=page.items,
            page=page_params.page,
            pageSize=page_params.page_size,
            total=page.total,
            asOf=page.as_of,
            filters=OpportunityFilters(
                market=market,
                horizon=horizon,
                sector=sector,
                industry=industry,
                marketCap=marketCap,
                minTrust=minTrust,
                minScore=minScore,
                minUpside=minUpside,
                liquidityBucket=liquidityBucket,
                status=status,
                search=search,
                sort=sort,
            ),
        )
    )
