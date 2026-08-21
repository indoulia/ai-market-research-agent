"""Query service backing GET /api/v1/discoveries (EPIC-M1.139).

For each stock, represents its single most-recently-discovered
`DiscoveryRecord` (across any scan/source), with market-cap/liquidity
classified **live** from the current `Stock`/`ScanCandidate` state (not
from M1.34's immutable `DiscoverySegment` snapshot) -- this endpoint is
"the discovery universe as currently known," not a point-in-time audit
view; the immutable snapshot remains available at the domain layer for
that purpose. `discoveryReasons` aggregates the rationale from every
`DiscoveryRecord` ever recorded for that stock (any scan/source), so a
stock discovered independently by multiple sources shows every reason.

Real keyset (cursor) pagination, matching M1.135's pattern, since the
discovery universe grows without bound over time.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    DiscoveryRecord,
    Prediction,
    PositiveOpportunityRanking,
    PredictionTrustScore,
    RecommendationGeneration,
    RecommendationLifecycle,
    ScanCandidate,
    Stock,
)
from app.recommendation_generator import OUTCOME_QUALIFIED

from ..errors import ValidationError
from ..pagination import DEFAULT_PAGE_SIZE
from ..schemas.discovery import STATUS_PENDING_ANALYSIS, DiscoveryItem
from .keyset import decode_cursor, encode_cursor, keyset_predicate
from .segmentation import liquidity_bucket_expr, market_cap_bucket_expr

SORT_FIELDS = ("discoveredAt", "score")
DIRECTIONS = ("asc", "desc")


@dataclass
class DiscoveryQuery:
    market: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_bucket: str | None = None
    liquidity: str | None = None
    min_score: Decimal | None = None
    sort: str = "discoveredAt"
    direction: str = "desc"
    page_size: int = DEFAULT_PAGE_SIZE
    cursor: str | None = None


@dataclass
class DiscoveryPage:
    items: list[DiscoveryItem]
    next_cursor: str | None


def list_discoveries(session: Session, query: DiscoveryQuery) -> DiscoveryPage:
    if query.sort not in SORT_FIELDS:
        raise ValidationError(f"Unknown sort field '{query.sort}'.", field_errors={"sort": f"must be one of {SORT_FIELDS}"})
    if query.direction not in DIRECTIONS:
        raise ValidationError(
            f"Unknown direction '{query.direction}'.", field_errors={"direction": f"must be one of {DIRECTIONS}"}
        )

    latest_ts = (
        select(DiscoveryRecord.stock_id, func.max(DiscoveryRecord.discovered_at).label("ts"))
        .group_by(DiscoveryRecord.stock_id)
        .subquery()
    )
    latest_ids = (
        select(func.max(DiscoveryRecord.id).label("id"))
        .join(latest_ts, (DiscoveryRecord.stock_id == latest_ts.c.stock_id) & (DiscoveryRecord.discovered_at == latest_ts.c.ts))
        .group_by(DiscoveryRecord.stock_id)
        .subquery()
    )

    latest_trust_ids = (
        select(PredictionTrustScore.prediction_id.label("prediction_id"), func.max(PredictionTrustScore.id).label("id"))
        .group_by(PredictionTrustScore.prediction_id)
        .subquery()
    )

    liquidity_expr = liquidity_bucket_expr(ScanCandidate.volume_ratio_20d)
    market_cap_expr = market_cap_bucket_expr(Stock.market_cap)

    stmt = (
        select(
            DiscoveryRecord.id.label("discovery_record_id"),
            DiscoveryRecord.stock_id,
            DiscoveryRecord.discovered_at,
            Stock.symbol,
            Stock.company_name,
            Stock.exchange,
            Stock.sector,
            Stock.industry,
            market_cap_expr.label("market_cap_bucket"),
            liquidity_expr.label("liquidity_bucket"),
            ScanCandidate.eligible,
            RecommendationGeneration.outcome,
            RecommendationLifecycle.state,
            PositiveOpportunityRanking.composite_score,
            PredictionTrustScore.overall_trust_score,
        )
        .select_from(DiscoveryRecord)
        .join(latest_ids, DiscoveryRecord.id == latest_ids.c.id)
        .join(Stock, Stock.id == DiscoveryRecord.stock_id)
        .outerjoin(
            ScanCandidate,
            (ScanCandidate.scan_id == DiscoveryRecord.scan_id) & (ScanCandidate.stock_id == DiscoveryRecord.stock_id),
        )
        .outerjoin(RecommendationGeneration, RecommendationGeneration.id == DiscoveryRecord.recommendation_generation_id)
        .outerjoin(Prediction, Prediction.id == RecommendationGeneration.prediction_id)
        .outerjoin(RecommendationLifecycle, RecommendationLifecycle.recommendation_generation_id == RecommendationGeneration.id)
        .outerjoin(
            PositiveOpportunityRanking,
            (PositiveOpportunityRanking.prediction_id == Prediction.id) & (PositiveOpportunityRanking.included.is_(True)),
        )
        .outerjoin(latest_trust_ids, latest_trust_ids.c.prediction_id == Prediction.id)
        .outerjoin(PredictionTrustScore, PredictionTrustScore.id == latest_trust_ids.c.id)
    )

    if query.market is not None:
        stmt = stmt.where(func.lower(Stock.exchange) == query.market.lower())
    if query.sector is not None:
        stmt = stmt.where(Stock.sector == query.sector)
    if query.industry is not None:
        stmt = stmt.where(Stock.industry == query.industry)
    if query.market_cap_bucket is not None:
        stmt = stmt.where(market_cap_expr == query.market_cap_bucket)
    if query.liquidity is not None:
        stmt = stmt.where(liquidity_expr == query.liquidity)
    if query.min_score is not None:
        stmt = stmt.where(PositiveOpportunityRanking.composite_score >= query.min_score)

    sort_expr = PositiveOpportunityRanking.composite_score if query.sort == "score" else DiscoveryRecord.discovered_at
    descending = query.direction == "desc"
    id_col = DiscoveryRecord.id

    if query.cursor:
        cursor_value, cursor_id = decode_cursor(query.cursor, is_datetime=query.sort == "discoveredAt")
        if cursor_value is not None:
            stmt = stmt.where(keyset_predicate(sort_expr, id_col, cursor_value, cursor_id, descending=descending))

    order_expr = sort_expr.desc() if descending else sort_expr.asc()
    id_order = id_col.desc() if descending else id_col.asc()
    stmt = stmt.order_by(order_expr, id_order).limit(query.page_size + 1)

    rows = session.execute(stmt).all()
    has_more = len(rows) > query.page_size
    rows = rows[: query.page_size]

    # discoveryReasons: every rationale ever recorded for this stock, oldest first.
    stock_ids = [row._mapping["stock_id"] for row in rows]
    reasons_by_stock: dict[int, list[str]] = {sid: [] for sid in stock_ids}
    if stock_ids:
        for stock_id, rationale in session.execute(
            select(DiscoveryRecord.stock_id, DiscoveryRecord.rationale)
            .where(DiscoveryRecord.stock_id.in_(stock_ids))
            .order_by(DiscoveryRecord.discovered_at.asc(), DiscoveryRecord.id.asc())
        ).all():
            reasons_by_stock[stock_id].append(rationale)

    items = []
    for row in rows:
        m = row._mapping
        if m["outcome"] == OUTCOME_QUALIFIED:
            status = m["state"] or STATUS_PENDING_ANALYSIS
        elif m["outcome"] is not None:
            status = m["outcome"]
        else:
            status = STATUS_PENDING_ANALYSIS
        items.append(
            DiscoveryItem(
                symbol=m["symbol"],
                companyName=m["company_name"],
                exchange=m["exchange"],
                sector=m["sector"] or "UNKNOWN",
                industry=m["industry"] or "UNKNOWN",
                marketCapBucket=m["market_cap_bucket"],
                liquidity=m["liquidity_bucket"],
                discoveredAt=m["discovered_at"],
                discoveryReasons=reasons_by_stock.get(m["stock_id"], []),
                score=m["composite_score"],
                trustScore=m["overall_trust_score"],
                eligibility=m["eligible"],
                status=status,
            )
        )

    next_cursor = None
    if has_more and rows:
        last = rows[-1]._mapping
        last_sort_value = last["composite_score"] if query.sort == "score" else last["discovered_at"]
        next_cursor = encode_cursor(last_sort_value, last["discovery_record_id"])

    return DiscoveryPage(items=items, next_cursor=next_cursor)
