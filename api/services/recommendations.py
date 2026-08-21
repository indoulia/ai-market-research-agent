"""Query service backing GET /api/v1/recommendations (EPIC-M1.135).

Composes existing, already-merged domain modules -- never recomputes a
signal another EPIC owns:
  - M1.87 ``PositiveOpportunityRanking`` (latest included batch) for
    ``score`` and the base "only positive eligible recommendations" set.
  - M1.15 ``RecommendationLifecycle`` (open states only) for the live feed.
  - M1.77 ``PredictionTrustScore`` (latest by id) for ``trustScore``.
  - M1.16 ``ConfidenceQualityClassification`` for ``uncertaintyLevel``
    (there is no separate uncertainty-quantification module yet; this is
    the closest existing, real vocabulary -- not invented for this EPIC).
  - M1.47 ``RecommendationPublication`` for ``targetPrice``/``stopLoss``/
    ``upsidePct`` when published, falling back to the raw prediction's
    own target/stop returns otherwise so a row is never dropped just
    because M1.47 hasn't published it.
  - M1.90's fundamentals/news/corporate-action tables for the four
    context summary fields, each a best-effort "latest available" value
    -- explicitly NOT a point-in-time-audited evidence snapshot. Absent
    data is reported as ``None``, never fabricated.

M1.124 (portfolio-aware utility/correlation) is APPROVED but not yet
implemented, so ``score``/ordering reflect M1.87's per-opportunity
composite only; no portfolio-level concentration/correlation adjustment
is applied here yet (see EPIC-M1.135's Dependencies note).

Pagination is real keyset (cursor) pagination on ``(sort_value, id)``,
not offset-based, so results stay stable while new rows are inserted
concurrently (AC: "pagination is cursor-based and stable during a query
session").
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.confidence_quality import CONFIDENCE_QUALITY_VERSION
from app.lifecycle import OPEN_STATES
from app.models import (
    ConfidenceQualityClassification,
    CorporateAction,
    FundamentalDataRecord,
    MarketPrice,
    MarketRegime,
    NewsEventRecord,
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
from ..schemas.recommendations import (
    EVIDENCE_FRESH,
    EVIDENCE_STALE,
    EVIDENCE_UNKNOWN,
    RECOMMENDATION_LABEL,
    PredictionVersions,
    RecommendationSummary,
)

# Market-cap bucket policy owned by this API layer -- no existing domain
# module defines one. Thresholds are on whatever unit Stock.market_cap is
# ingested in; versioned so a future retune is a visible contract change.
MARKET_CAP_BUCKET_VERSION = "MCB-001"
LARGE_CAP = "LARGE_CAP"
MID_CAP = "MID_CAP"
SMALL_CAP = "SMALL_CAP"
_LARGE_CAP_MIN = Decimal("200000000000")
_MID_CAP_MIN = Decimal("50000000000")

SORT_FIELDS = ("score", "trust", "upside", "confidence", "updatedAt")
DIRECTIONS = ("asc", "desc")


@dataclass
class RecommendationQuery:
    horizon: int | None = None
    market: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_bucket: str | None = None
    min_score: Decimal | None = None
    min_trust: Decimal | None = None
    sort: str = "score"
    direction: str = "desc"
    page_size: int = DEFAULT_PAGE_SIZE
    cursor: str | None = None


@dataclass
class RecommendationPage:
    items: list[RecommendationSummary]
    next_cursor: str | None


def _market_cap_bucket_expr():
    return case(
        (Stock.market_cap.is_(None), None),
        (Stock.market_cap >= _LARGE_CAP_MIN, LARGE_CAP),
        (Stock.market_cap >= _MID_CAP_MIN, MID_CAP),
        else_=SMALL_CAP,
    )


def _sort_expr(sort: str, *, publication, trust, lifecycle):
    if sort == "score":
        return PositiveOpportunityRanking.composite_score
    if sort == "trust":
        return trust.overall_trust_score
    if sort == "upside":
        return func.coalesce(publication.upside_percentage, Prediction.target_return * 100)
    if sort == "confidence":
        return Prediction.confidence
    if sort == "updatedAt":
        return func.coalesce(lifecycle.last_checked_at, lifecycle.created_at)
    raise ValidationError(f"Unknown sort field '{sort}'.", field_errors={"sort": f"must be one of {SORT_FIELDS}"})


def _encode_cursor(sort_value, row_id: int) -> str:
    if isinstance(sort_value, datetime):
        serialized = sort_value.isoformat()
    elif isinstance(sort_value, Decimal):
        serialized = str(sort_value)
    elif sort_value is None:
        serialized = None
    else:
        serialized = str(sort_value)
    raw = json.dumps({"v": serialized, "id": row_id}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str, sort: str) -> tuple[object, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw)
        value, row_id = payload["v"], int(payload["id"])
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValidationError("Invalid cursor.", field_errors={"cursor": "malformed"}) from exc

    if value is None:
        return None, row_id
    try:
        if sort == "updatedAt":
            return datetime.fromisoformat(value), row_id
        return Decimal(value), row_id
    except (ValueError, InvalidOperation) as exc:
        raise ValidationError("Invalid cursor.", field_errors={"cursor": "malformed"}) from exc


def _keyset_predicate(sort_expr, id_col, cursor_value, cursor_id: int, *, descending: bool):
    # The `id_col != cursor_id` guard is load-bearing, not defensive
    # decoration: SQLite stores Numeric columns as raw floats, and
    # SQLAlchemy quantizes the *Python* Decimal it hands back to the
    # column's declared scale (6 places) -- so the cursor's sort value
    # (derived from that quantized Decimal) can differ from the row's
    # true stored value by less than one part in a million. That's
    # normally invisible, but it means the previous page's own boundary
    # row can spuriously satisfy `sort_expr < cursor_value` again on the
    # next page. Excluding the boundary row's id explicitly closes that
    # hole regardless of the comparison outcome.
    if descending:
        return and_(
            or_(sort_expr < cursor_value, and_(sort_expr == cursor_value, id_col < cursor_id)),
            id_col != cursor_id,
        )
    return and_(
        or_(sort_expr > cursor_value, and_(sort_expr == cursor_value, id_col > cursor_id)),
        id_col != cursor_id,
    )


def _latest_market_price_pair(session: Session, stock_id: int) -> tuple[Decimal | None, Decimal | None]:
    rows = session.execute(
        select(MarketPrice.close)
        .where(MarketPrice.stock_id == stock_id)
        .order_by(MarketPrice.timestamp.desc())
        .limit(2)
    ).scalars().all()
    if not rows:
        return None, None
    price = rows[0]
    if len(rows) < 2 or rows[1] == 0:
        return price, None
    change_pct = (price - rows[1]) / rows[1] * 100
    return price, change_pct


def _fundamental_summary(session: Session, stock_id: int) -> str | None:
    record = session.scalar(
        select(FundamentalDataRecord)
        .where(FundamentalDataRecord.stock_id == stock_id)
        .order_by(FundamentalDataRecord.published_at.desc())
        .limit(1)
    )
    if record is None:
        return None
    parts = []
    if record.pe_ratio is not None:
        parts.append(f"P/E {record.pe_ratio}")
    if record.eps is not None:
        parts.append(f"EPS {record.eps}")
    if record.debt_to_equity is not None:
        parts.append(f"D/E {record.debt_to_equity}")
    return ", ".join(parts) if parts else None


def _news_summary(session: Session, stock_id: int) -> str | None:
    record = session.scalar(
        select(NewsEventRecord)
        .where(NewsEventRecord.stock_id == stock_id)
        .order_by(NewsEventRecord.published_at.desc())
        .limit(1)
    )
    return record.headline if record is not None else None


def _event_summary(session: Session, stock_id: int) -> str | None:
    record = session.scalar(
        select(CorporateAction)
        .where(CorporateAction.stock_id == stock_id)
        .order_by(CorporateAction.effective_date.desc())
        .limit(1)
    )
    if record is None:
        return None
    return f"{record.action_type} effective {record.effective_date.isoformat()}"


def _market_summary(session: Session, scan_id: int | None) -> str | None:
    if scan_id is None:
        return None
    regime = session.scalar(select(MarketRegime).where(MarketRegime.scan_id == scan_id))
    return f"Market regime: {regime.regime}" if regime is not None else None


def _evidence_freshness(session: Session, prediction_id: int) -> str:
    items = session.execute(
        select(RecommendationEvidenceItem.is_stale).where(RecommendationEvidenceItem.prediction_id == prediction_id)
    ).scalars().all()
    if not items:
        return EVIDENCE_UNKNOWN
    return EVIDENCE_STALE if any(items) else EVIDENCE_FRESH


def list_recommendations(session: Session, query: RecommendationQuery) -> RecommendationPage:
    if query.sort not in SORT_FIELDS:
        raise ValidationError(f"Unknown sort field '{query.sort}'.", field_errors={"sort": f"must be one of {SORT_FIELDS}"})
    if query.direction not in DIRECTIONS:
        raise ValidationError(
            f"Unknown direction '{query.direction}'.", field_errors={"direction": f"must be one of {DIRECTIONS}"}
        )

    latest_evaluated_at = session.scalar(select(func.max(PositiveOpportunityRanking.evaluated_at)))
    if latest_evaluated_at is None:
        return RecommendationPage(items=[], next_cursor=None)

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
            RecommendationLifecycle.state.in_(OPEN_STATES),
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
        stmt = stmt.where(_market_cap_bucket_expr() == query.market_cap_bucket)
    if query.min_score is not None:
        stmt = stmt.where(PositiveOpportunityRanking.composite_score >= query.min_score)
    if query.min_trust is not None:
        stmt = stmt.where(trust.overall_trust_score >= query.min_trust)

    sort_expr = _sort_expr(query.sort, publication=RecommendationPublication, trust=trust, lifecycle=RecommendationLifecycle)
    descending = query.direction == "desc"
    id_col = RecommendationGeneration.id

    if query.cursor:
        cursor_value, cursor_id = _decode_cursor(query.cursor, query.sort)
        if cursor_value is not None:
            stmt = stmt.where(_keyset_predicate(sort_expr, id_col, cursor_value, cursor_id, descending=descending))

    order_expr = sort_expr.desc() if descending else sort_expr.asc()
    id_order = id_col.desc() if descending else id_col.asc()
    stmt = stmt.order_by(order_expr, id_order).limit(query.page_size + 1)

    rows = session.execute(stmt).all()
    has_more = len(rows) > query.page_size
    rows = rows[: query.page_size]

    items = []
    for row in rows:
        m = row._mapping
        price, change_pct = _latest_market_price_pair(session, m["stock_id"])
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
                fundamentalSummary=_fundamental_summary(session, m["stock_id"]),
                newsSummary=_news_summary(session, m["stock_id"]),
                eventSummary=_event_summary(session, m["stock_id"]),
                marketSummary=_market_summary(session, m["scan_id"]),
                evidenceFreshness=_evidence_freshness(session, m["prediction_id"]),
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

    next_cursor = None
    if has_more and rows:
        last = rows[-1]._mapping
        last_sort_value = {
            "score": last["composite_score"],
            "trust": last["overall_trust_score"],
            "upside": last["upside_percentage"] if last["upside_percentage"] is not None else last["target_return"] * 100,
            "confidence": last["confidence"],
            "updatedAt": last["last_checked_at"] or last["lifecycle_created_at"],
        }[query.sort]
        next_cursor = _encode_cursor(last_sort_value, last["recommendation_id"])

    return RecommendationPage(items=items, next_cursor=next_cursor)
