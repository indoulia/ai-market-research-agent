"""Query service backing GET /api/v1/opportunities (EPIC-M3.3).

Composes the same already-merged domain modules M1.135's
``list_recommendations`` does (see ``api/services/recommendations.py`` for
the detailed provenance of each field) -- this endpoint does not
recompute anything, it exposes the same positive-opportunity universe
through a search/filter/sort/pagination-richer, page-based contract
suited to a dedicated "Opportunity Explorer" screen rather than a
dashboard feed:

  - Page-based pagination (``page``/``pageSize`` + a real ``total`` count)
    instead of M1.135's cursor pagination, per this EPIC's own contract.
    A real ``COUNT(*)`` is affordable here (M1.135 deliberately avoided
    one for its own limit+1 keyset approach) because this endpoint's own
    acceptance criteria explicitly requires ``total`` in the response.
  - Additional filters M1.135 doesn't expose: ``minUpside``,
    ``liquidityBucket`` (reusing the same ``liquidity_bucket_expr`` M1.139's
    ``/discoveries`` endpoint already uses over ``ScanCandidate.volume_ratio_20d``),
    ``status`` (restricted to the two open lifecycle states -- this is an
    *opportunity* explorer, not a historical archive; that is M3.4/M3.8's
    job), and server-side ``search`` over symbol/company name.
  - Additional sort keys: ``probability`` (``Prediction.predicted_probability``),
    ``freshness`` (a SQL-computable proxy for the same FRESH/STALE/UNKNOWN
    definition ``context_summaries.evidence_freshness`` already uses, so a
    row that would score STALE sorts as the least fresh), and ``ranking``
    (identical to ``score`` -- ``app/opportunity_ranking.py`` sorts its own
    output by ``-composite_score``, so "the platform's ranking order" and
    "the composite score" are the same value, not two different fields).

``marketCap`` is accepted as the same bucket vocabulary
(``LARGE_CAP``/``MID_CAP``/``SMALL_CAP``/``UNCLASSIFIED``) as M1.135's
``marketCapBucket`` -- no other market-cap vocabulary (e.g. a raw numeric
range) exists anywhere in this codebase to give the epic's shorter
parameter name a different meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.confidence_quality import CONFIDENCE_QUALITY_VERSION
from app.lifecycle import OPEN_STATES
from app.models import (
    ConfidenceQualityClassification,
    Prediction,
    PositiveOpportunityRanking,
    PredictionTrustScore,
    RecommendationEvidenceItem,
    RecommendationGeneration,
    RecommendationLifecycle,
    RecommendationPublication,
    ScanCandidate,
    Stock,
)
from app.opportunity_ranking import OPPORTUNITY_RANKING_VERSION
from app.target_stop_loss import TARGET_STOP_METHODOLOGY_VERSION

from ..errors import ValidationError
from ..pagination import DEFAULT_PAGE_SIZE
from ..schemas.recommendations import RECOMMENDATION_LABEL, PredictionVersions, RecommendationSummary
from .context_summaries import (
    event_summary,
    evidence_freshness,
    fundamental_summary,
    latest_market_price_pairs,
    market_summary,
    news_summary,
)
from .segmentation import liquidity_bucket_expr, market_cap_bucket_expr

SORT_FIELDS = ("trust", "score", "upside", "probability", "freshness", "ranking")
DEFAULT_SORT = "-score"


@dataclass
class OpportunityQuery:
    market: str | None = None
    horizon: int | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_bucket: str | None = None
    min_trust: Decimal | None = None
    min_score: Decimal | None = None
    min_upside: Decimal | None = None
    liquidity_bucket: str | None = None
    status: str | None = None
    search: str | None = None
    sort: str = DEFAULT_SORT
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass
class OpportunityPage:
    items: list[RecommendationSummary]
    total: int
    as_of: datetime | None


def _parse_sort(sort: str) -> tuple[str, bool]:
    descending = sort.startswith("-")
    sort_field = sort[1:] if descending else sort
    if sort_field not in SORT_FIELDS:
        raise ValidationError(
            f"Unknown sort field '{sort_field}'.",
            field_errors={"sort": f"must be one of {SORT_FIELDS}, optionally prefixed with '-' for descending"},
        )
    return sort_field, descending


def _upside_expr(publication):
    return func.coalesce(publication.upside_percentage, Prediction.target_return * 100)


def _freshness_rank_expr():
    """SQL-computable proxy for ``context_summaries.evidence_freshness``:
    STALE (any recorded category stale) ranks lowest, FRESH highest,
    UNKNOWN (no evidence item ever recorded) in between -- matching that
    function's own precedence exactly."""
    ev = RecommendationEvidenceItem
    stale_exists = exists(select(1).where(ev.prediction_id == Prediction.id, ev.is_stale.is_(True)))
    any_exists = exists(select(1).where(ev.prediction_id == Prediction.id))
    return case((stale_exists, 0), (any_exists, 2), else_=1)


def _sort_expr(sort_field: str, *, trust):
    if sort_field in ("score", "ranking"):
        return PositiveOpportunityRanking.composite_score
    if sort_field == "trust":
        return trust.overall_trust_score
    if sort_field == "upside":
        return _upside_expr(RecommendationPublication)
    if sort_field == "probability":
        return Prediction.predicted_probability
    if sort_field == "freshness":
        return _freshness_rank_expr()
    raise ValidationError(f"Unknown sort field '{sort_field}'.", field_errors={"sort": f"must be one of {SORT_FIELDS}"})


def list_opportunities(session: Session, query: OpportunityQuery) -> OpportunityPage:
    sort_field, descending = _parse_sort(query.sort)

    if query.status is not None and query.status not in OPEN_STATES:
        raise ValidationError(
            f"Unknown status '{query.status}'.",
            field_errors={"status": f"must be one of {OPEN_STATES} -- this endpoint is a live opportunity feed, not a historical archive"},
        )
    lifecycle_states = (query.status,) if query.status is not None else OPEN_STATES

    latest_evaluated_at = session.scalar(select(func.max(PositiveOpportunityRanking.evaluated_at)))
    if latest_evaluated_at is None:
        return OpportunityPage(items=[], total=0, as_of=None)

    latest_trust_ids = (
        select(PredictionTrustScore.prediction_id.label("prediction_id"), func.max(PredictionTrustScore.id).label("id"))
        .group_by(PredictionTrustScore.prediction_id)
        .subquery()
    )
    trust = PredictionTrustScore

    stmt = (
        select(
            RecommendationGeneration.id.label("recommendation_id"),
            Stock.id.label("stock_id"),
            Stock.symbol,
            Stock.exchange,
            Stock.company_name,
            Prediction.id.label("prediction_id"),
            Prediction.as_of_timestamp,
            Prediction.entry_price,
            Prediction.horizon_days,
            Prediction.target_return,
            Prediction.stop_return,
            Prediction.predicted_probability,
            Prediction.confidence,
            Prediction.model_version,
            Prediction.feature_version,
            Prediction.consensus_contract_version,
            Prediction.horizon_selection_version,
            Prediction.scoring_contract_version,
            PositiveOpportunityRanking.composite_score,
            RecommendationLifecycle.state,
            RecommendationLifecycle.last_checked_at,
            RecommendationLifecycle.created_at.label("lifecycle_created_at"),
            RecommendationPublication.target_price,
            RecommendationPublication.stop_loss_price,
            RecommendationPublication.upside_percentage,
            trust.overall_trust_score,
            ConfidenceQualityClassification.quality,
            ScanCandidate.scan_id,
        )
        .select_from(PositiveOpportunityRanking)
        .join(Prediction, Prediction.id == PositiveOpportunityRanking.prediction_id)
        .join(Stock, Stock.id == Prediction.stock_id)
        .join(RecommendationGeneration, RecommendationGeneration.prediction_id == Prediction.id)
        .join(RecommendationLifecycle, RecommendationLifecycle.recommendation_generation_id == RecommendationGeneration.id)
        .join(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
        .outerjoin(
            RecommendationPublication,
            and_(
                RecommendationPublication.prediction_id == Prediction.id,
                RecommendationPublication.methodology_version == TARGET_STOP_METHODOLOGY_VERSION,
            ),
        )
        .outerjoin(latest_trust_ids, latest_trust_ids.c.prediction_id == Prediction.id)
        .outerjoin(trust, trust.id == latest_trust_ids.c.id)
        .outerjoin(
            ConfidenceQualityClassification,
            and_(
                ConfidenceQualityClassification.prediction_id == Prediction.id,
                ConfidenceQualityClassification.classification_rule_version == CONFIDENCE_QUALITY_VERSION,
            ),
        )
        .where(
            PositiveOpportunityRanking.included.is_(True),
            PositiveOpportunityRanking.evaluated_at == latest_evaluated_at,
            RecommendationLifecycle.state.in_(lifecycle_states),
        )
    )

    if query.horizon is not None:
        stmt = stmt.where(Prediction.horizon_days == query.horizon)
    if query.market is not None:
        stmt = stmt.where(func.lower(Stock.exchange) == query.market.lower())
    if query.sector is not None:
        stmt = stmt.where(Stock.sector == query.sector)
    if query.industry is not None:
        stmt = stmt.where(Stock.industry == query.industry)
    if query.market_cap_bucket is not None:
        stmt = stmt.where(market_cap_bucket_expr(Stock.market_cap) == query.market_cap_bucket)
    if query.liquidity_bucket is not None:
        stmt = stmt.where(liquidity_bucket_expr(ScanCandidate.volume_ratio_20d) == query.liquidity_bucket)
    if query.min_score is not None:
        stmt = stmt.where(PositiveOpportunityRanking.composite_score >= query.min_score)
    if query.min_trust is not None:
        stmt = stmt.where(trust.overall_trust_score >= query.min_trust)
    if query.min_upside is not None:
        stmt = stmt.where(_upside_expr(RecommendationPublication) >= query.min_upside)
    if query.search:
        needle = f"%{query.search}%"
        stmt = stmt.where(or_(Stock.symbol.ilike(needle), Stock.company_name.ilike(needle)))

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    sort_expr = _sort_expr(sort_field, trust=trust)
    order_expr = sort_expr.desc() if descending else sort_expr.asc()
    id_col = RecommendationGeneration.id
    id_order = id_col.desc() if descending else id_col.asc()
    offset = (query.page - 1) * query.page_size
    stmt = stmt.order_by(order_expr, id_order).offset(offset).limit(query.page_size)

    rows = session.execute(stmt).all()
    price_pairs = latest_market_price_pairs(session, [row._mapping["stock_id"] for row in rows])

    items = []
    for row in rows:
        m = row._mapping
        price, change_pct = price_pairs[m["stock_id"]]
        target_price = m["target_price"] if m["target_price"] is not None else m["entry_price"] * (1 + m["target_return"])
        stop_loss = m["stop_loss_price"] if m["stop_loss_price"] is not None else m["entry_price"] * (1 + m["stop_return"])
        upside_pct = m["upside_percentage"] if m["upside_percentage"] is not None else m["target_return"] * 100

        items.append(
            RecommendationSummary(
                id=m["recommendation_id"],
                symbol=m["symbol"],
                exchange=m["exchange"],
                companyName=m["company_name"],
                asOf=m["as_of_timestamp"],
                price=price,
                changePct=change_pct,
                recommendation=RECOMMENDATION_LABEL,
                horizonDays=m["horizon_days"],
                targetPrice=target_price,
                stopLoss=stop_loss,
                upsidePct=upside_pct,
                probability=m["predicted_probability"],
                score=m["composite_score"],
                confidence=m["confidence"],
                trustScore=m["overall_trust_score"],
                uncertaintyLevel=m["quality"],
                fundamentalSummary=fundamental_summary(session, m["stock_id"]),
                newsSummary=news_summary(session, m["stock_id"]),
                eventSummary=event_summary(session, m["stock_id"]),
                marketSummary=market_summary(session, m["scan_id"]),
                evidenceFreshness=evidence_freshness(session, m["prediction_id"]),
                status=m["state"],
                predictionVersion=PredictionVersions(
                    modelVersion=m["model_version"],
                    featureVersion=m["feature_version"],
                    consensusContractVersion=m["consensus_contract_version"],
                    horizonSelectionVersion=m["horizon_selection_version"],
                    scoringContractVersion=m["scoring_contract_version"],
                    rankingVersion=OPPORTUNITY_RANKING_VERSION,
                ),
                updatedAt=m["last_checked_at"] or m["lifecycle_created_at"],
            )
        )

    return OpportunityPage(items=items, total=total, as_of=latest_evaluated_at)
