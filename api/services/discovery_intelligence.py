"""Query services backing GET /api/v1/discovery/{summary,history,candidates}
(EPIC-M3.6).

Read-only compositions over already-merged, already-tested tables and
modules -- nothing about the discovery/qualification/publication pipeline
is recomputed here:
  - `app.models.DiscoveryRecord`/`ScanCandidate`/`RecommendationGeneration`/
    `PositiveOpportunityRanking`/`RecommendationSelection` (M1.12/M1.13/
    M1.17/M1.19) supply the discovered -> analyzed -> qualified/suppressed
    -> published funnel this EPIC's UI Scope asks to make visible.
  - `app.discovery_effectiveness.compute_discovery_effectiveness_report`
    (M1.28) supplies the "discovery effectiveness summary" verbatim -- its
    per-source funnel/success-rate/verdict logic is reused unchanged, only
    reprojected into `DiscoverySourceEffectiveness` (camelCase DTO).
  - `api/services/discovery.py` (M1.139) is the sibling, already-shipped
    `GET /api/v1/discoveries` endpoint over the same tables. This module
    intentionally does not import from it (and does not touch it): M3.6's
    API Contract names three specific new paths whose response shapes
    (`lifecycleStage`, `suppressionReason`, per-source funnel counts) are
    genuinely different projections, not aliases -- adding them here avoids
    any risk of changing M1.139's existing, tested contract.

Lifecycle stage classification (`_stage_expr`), in priority order:
  1. `ScanCandidate.eligible is False` -> SUPPRESSED (excluded by the scan's
     own universe screen, before any consensus/scoring ever ran).
  2. No `RecommendationGeneration` yet -> DISCOVERED (M1.139's
     `PENDING_ANALYSIS`, renamed for this EPIC's own vocabulary).
  3. `outcome == NOT_QUALIFIED` -> SUPPRESSED (consensus/score gate not
     met).
  4. Ever `RecommendationSelection.selected` -> PUBLISHED.
  5. Latest `PositiveOpportunityRanking.included is False` -> SUPPRESSED
     (qualified, but excluded from the published ranking -- e.g. sector
     concentration limit, duplicate-stock lower score).
  6. Otherwise -> QUALIFIED.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session

from app.discovery_effectiveness import compute_discovery_effectiveness_report
from app.models import (
    DailyCandidateScan,
    DiscoveryRecord,
    Prediction,
    PositiveOpportunityRanking,
    PredictionTrustScore,
    RecommendationGeneration,
    RecommendationSelection,
    ScanCandidate,
    Stock,
)
from app.recommendation_generator import OUTCOME_NOT_QUALIFIED, OUTCOME_QUALIFIED

from ..errors import ValidationError
from ..pagination import DEFAULT_PAGE_SIZE
from ..schemas.discovery import (
    LIFECYCLE_DISCOVERED,
    LIFECYCLE_PUBLISHED,
    LIFECYCLE_QUALIFIED,
    LIFECYCLE_SUPPRESSED,
    DiscoveryCandidate,
    DiscoveryFunnelCounts,
    DiscoveryHistoryPoint,
    DiscoverySourceEffectiveness,
    DiscoverySummary,
)
from .keyset import decode_cursor, encode_cursor, keyset_predicate
from .segmentation import liquidity_bucket_expr, market_cap_bucket_expr

DEFAULT_HISTORY_DAYS = 30
MAX_HISTORY_DAYS = 180


def _latest_discovery_record_ids():
    """Same "one row per stock, most-recently-discovered" collapse as
    `api/services/discovery.py::list_discoveries` -- a stock discovered by
    more than one source/scan must still contribute exactly one row to any
    count or list here."""
    latest_ts = (
        select(DiscoveryRecord.stock_id, func.max(DiscoveryRecord.discovered_at).label("ts"))
        .group_by(DiscoveryRecord.stock_id)
        .subquery()
    )
    return (
        select(func.max(DiscoveryRecord.id).label("id"))
        .join(latest_ts, (DiscoveryRecord.stock_id == latest_ts.c.stock_id) & (DiscoveryRecord.discovered_at == latest_ts.c.ts))
        .group_by(DiscoveryRecord.stock_id)
        .subquery()
    )


def _latest_ranking_ids():
    return (
        select(PositiveOpportunityRanking.prediction_id.label("prediction_id"), func.max(PositiveOpportunityRanking.id).label("id"))
        .group_by(PositiveOpportunityRanking.prediction_id)
        .subquery()
    )


def _candidate_rows_subquery():
    """The full, unfiltered discovery-universe query with every column
    needed by both the candidates list and the summary funnel counts,
    wrapped as a subquery so both callers filter/aggregate over identical
    joins (never two divergent copies of this join graph)."""
    latest_ids = _latest_discovery_record_ids()
    latest_ranking_ids = _latest_ranking_ids()

    market_cap_expr = market_cap_bucket_expr(Stock.market_cap)
    liquidity_expr = liquidity_bucket_expr(ScanCandidate.volume_ratio_20d)

    published_expr = exists(
        select(RecommendationSelection.id).where(
            RecommendationSelection.recommendation_generation_id == RecommendationGeneration.id,
            RecommendationSelection.selected.is_(True),
        )
    )

    stage_expr = case(
        (ScanCandidate.eligible.is_(False), LIFECYCLE_SUPPRESSED),
        (RecommendationGeneration.outcome.is_(None), LIFECYCLE_DISCOVERED),
        (RecommendationGeneration.outcome == OUTCOME_NOT_QUALIFIED, LIFECYCLE_SUPPRESSED),
        (published_expr, LIFECYCLE_PUBLISHED),
        (PositiveOpportunityRanking.included.is_(False), LIFECYCLE_SUPPRESSED),
        else_=LIFECYCLE_QUALIFIED,
    )

    stmt = (
        select(
            DiscoveryRecord.id.label("discovery_record_id"),
            DiscoveryRecord.stock_id.label("stock_id"),
            DiscoveryRecord.discovered_at.label("discovered_at"),
            Stock.symbol.label("symbol"),
            Stock.company_name.label("company_name"),
            Stock.exchange.label("exchange"),
            Stock.sector.label("sector"),
            Stock.industry.label("industry"),
            market_cap_expr.label("market_cap_bucket"),
            liquidity_expr.label("liquidity_bucket"),
            ScanCandidate.eligible.label("eligible"),
            ScanCandidate.exclusion_reason.label("exclusion_reason"),
            RecommendationGeneration.outcome.label("outcome"),
            RecommendationGeneration.failed_criteria.label("failed_criteria"),
            PositiveOpportunityRanking.included.label("ranking_included"),
            PositiveOpportunityRanking.exclusion_reason.label("ranking_exclusion_reason"),
            PositiveOpportunityRanking.composite_score.label("composite_score"),
            PredictionTrustScore.overall_trust_score.label("overall_trust_score"),
            Prediction.id.label("prediction_id"),
            stage_expr.label("stage"),
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
        .outerjoin(latest_ranking_ids, latest_ranking_ids.c.prediction_id == Prediction.id)
        .outerjoin(PositiveOpportunityRanking, PositiveOpportunityRanking.id == latest_ranking_ids.c.id)
        .outerjoin(PredictionTrustScore, PredictionTrustScore.prediction_id == Prediction.id)
    )
    return stmt.subquery()


def _suppression_reason(row: dict) -> str | None:
    if row["stage"] != LIFECYCLE_SUPPRESSED:
        return None
    if row["eligible"] is False:
        return row["exclusion_reason"] or "INELIGIBLE"
    if row["outcome"] == OUTCOME_NOT_QUALIFIED:
        failed = row["failed_criteria"]
        return ",".join(failed) if failed else "CONSENSUS_NOT_MET"
    return row["ranking_exclusion_reason"] or "RANKING_EXCLUDED"


@dataclass
class CandidateQuery:
    market: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_bucket: str | None = None
    discovery_basis: str | None = None
    discovered_from: date | None = None
    discovered_to: date | None = None
    page_size: int = DEFAULT_PAGE_SIZE
    cursor: str | None = None


@dataclass
class CandidatePage:
    items: list[DiscoveryCandidate]
    next_cursor: str | None


def list_discovery_candidates(session: Session, query: CandidateQuery) -> CandidatePage:
    subq = _candidate_rows_subquery()
    stmt = select(subq)

    if query.market is not None:
        stmt = stmt.where(func.lower(subq.c.exchange) == query.market.lower())
    if query.sector is not None:
        stmt = stmt.where(subq.c.sector == query.sector)
    if query.industry is not None:
        stmt = stmt.where(subq.c.industry == query.industry)
    if query.market_cap_bucket is not None:
        stmt = stmt.where(subq.c.market_cap_bucket == query.market_cap_bucket)
    if query.discovery_basis is not None:
        stmt = stmt.where(
            subq.c.stock_id.in_(select(DiscoveryRecord.stock_id).where(DiscoveryRecord.source == query.discovery_basis))
        )
    if query.discovered_from is not None:
        stmt = stmt.where(subq.c.discovered_at >= datetime.combine(query.discovered_from, time.min, tzinfo=timezone.utc))
    if query.discovered_to is not None:
        # Inclusive of the whole `discovered_to` day.
        stmt = stmt.where(
            subq.c.discovered_at < datetime.combine(query.discovered_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        )

    if query.cursor:
        cursor_value, cursor_id = decode_cursor(query.cursor, is_datetime=True)
        if cursor_value is not None:
            stmt = stmt.where(keyset_predicate(subq.c.discovered_at, subq.c.discovery_record_id, cursor_value, cursor_id, descending=True))

    stmt = stmt.order_by(subq.c.discovered_at.desc(), subq.c.discovery_record_id.desc()).limit(query.page_size + 1)

    rows = [r._mapping for r in session.execute(stmt).all()]
    has_more = len(rows) > query.page_size
    rows = rows[: query.page_size]

    stock_ids = [r["stock_id"] for r in rows]
    reasons_by_stock: dict[int, list[str]] = {sid: [] for sid in stock_ids}
    sources_by_stock: dict[int, list[str]] = {sid: [] for sid in stock_ids}
    if stock_ids:
        for stock_id, rationale, source in session.execute(
            select(DiscoveryRecord.stock_id, DiscoveryRecord.rationale, DiscoveryRecord.source)
            .where(DiscoveryRecord.stock_id.in_(stock_ids))
            .order_by(DiscoveryRecord.discovered_at.asc(), DiscoveryRecord.id.asc())
        ).all():
            reasons_by_stock[stock_id].append(rationale)
            if source not in sources_by_stock[stock_id]:
                sources_by_stock[stock_id].append(source)

    items = [
        DiscoveryCandidate(
            candidateId=r["discovery_record_id"],
            symbol=r["symbol"],
            companyName=r["company_name"],
            exchange=r["exchange"],
            sector=r["sector"] or "UNKNOWN",
            industry=r["industry"] or "UNKNOWN",
            marketCapBucket=r["market_cap_bucket"],
            liquidity=r["liquidity_bucket"],
            discoveredAt=r["discovered_at"],
            discoverySources=sources_by_stock.get(r["stock_id"], []),
            discoveryReasons=reasons_by_stock.get(r["stock_id"], []),
            score=r["composite_score"],
            trustScore=r["overall_trust_score"],
            lifecycleStage=r["stage"],
            suppressionReason=_suppression_reason(r),
            publishedRecommendationId=r["prediction_id"] if r["stage"] == LIFECYCLE_PUBLISHED else None,
        )
        for r in rows
    ]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode_cursor(last["discovered_at"], last["discovery_record_id"])

    return CandidatePage(items=items, next_cursor=next_cursor)


def get_discovery_summary(session: Session) -> DiscoverySummary:
    subq = _candidate_rows_subquery()
    rows = session.execute(select(subq.c.stage, func.count().label("cnt")).group_by(subq.c.stage)).all()
    counts = {LIFECYCLE_DISCOVERED: 0, LIFECYCLE_QUALIFIED: 0, LIFECYCLE_SUPPRESSED: 0, LIFECYCLE_PUBLISHED: 0}
    for stage, cnt in rows:
        counts[stage] = cnt

    discovered_total = sum(counts.values())
    analyzed_total = counts[LIFECYCLE_QUALIFIED] + counts[LIFECYCLE_SUPPRESSED] + counts[LIFECYCLE_PUBLISHED]
    funnel = DiscoveryFunnelCounts(
        discovered=discovered_total,
        analyzed=analyzed_total,
        qualified=counts[LIFECYCLE_QUALIFIED],
        suppressed=counts[LIFECYCLE_SUPPRESSED],
        published=counts[LIFECYCLE_PUBLISHED],
    )

    effectiveness = compute_discovery_effectiveness_report(session)
    by_source = [
        DiscoverySourceEffectiveness(
            source=f.source,
            discoveredCount=f.discovered_count,
            analyzedCount=f.routed_count,
            rejectedCount=f.rejected_count,
            qualifiedCount=f.qualified_count,
            evaluatedCount=f.evaluated_count,
            successCount=f.success_count,
            failureCount=f.failure_count,
            unevaluableCount=f.unevaluable_count,
            openCount=f.open_count,
            successRate=f.success_rate,
            verdict=f.verdict,
        )
        for f in effectiveness.by_source
    ]

    return DiscoverySummary(
        asOf=datetime.now(timezone.utc),
        counts=funnel,
        effectivenessBySource=by_source,
        effectivenessReportVersion=effectiveness.report_version,
    )


@dataclass
class HistoryQuery:
    days: int = DEFAULT_HISTORY_DAYS


def get_discovery_history(session: Session, query: HistoryQuery) -> list[DiscoveryHistoryPoint]:
    if query.days < 1 or query.days > MAX_HISTORY_DAYS:
        raise ValidationError(
            f"'days' must be between 1 and {MAX_HISTORY_DAYS}.", field_errors={"days": f"must be 1..{MAX_HISTORY_DAYS}"}
        )

    discovered_by_scan = (
        select(DiscoveryRecord.scan_id.label("scan_id"), func.count(func.distinct(DiscoveryRecord.stock_id)).label("cnt"))
        .group_by(DiscoveryRecord.scan_id)
        .subquery()
    )
    analyzed_by_scan = (
        select(
            ScanCandidate.scan_id.label("scan_id"),
            func.count(RecommendationGeneration.id).label("analyzed"),
            func.sum(case((RecommendationGeneration.outcome == OUTCOME_QUALIFIED, 1), else_=0)).label("qualified"),
            func.sum(case((RecommendationGeneration.outcome == OUTCOME_NOT_QUALIFIED, 1), else_=0)).label("suppressed"),
        )
        .select_from(ScanCandidate)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .group_by(ScanCandidate.scan_id)
        .subquery()
    )
    published_by_scan = (
        select(
            RecommendationSelection.scan_id.label("scan_id"),
            func.count(func.distinct(RecommendationSelection.recommendation_generation_id)).label("published"),
        )
        .where(RecommendationSelection.selected.is_(True))
        .group_by(RecommendationSelection.scan_id)
        .subquery()
    )

    stmt = (
        select(
            DailyCandidateScan.scan_date,
            func.coalesce(discovered_by_scan.c.cnt, 0),
            func.coalesce(analyzed_by_scan.c.analyzed, 0),
            func.coalesce(analyzed_by_scan.c.qualified, 0),
            func.coalesce(analyzed_by_scan.c.suppressed, 0),
            func.coalesce(published_by_scan.c.published, 0),
        )
        .select_from(DailyCandidateScan)
        .outerjoin(discovered_by_scan, discovered_by_scan.c.scan_id == DailyCandidateScan.id)
        .outerjoin(analyzed_by_scan, analyzed_by_scan.c.scan_id == DailyCandidateScan.id)
        .outerjoin(published_by_scan, published_by_scan.c.scan_id == DailyCandidateScan.id)
        .order_by(DailyCandidateScan.scan_date.desc())
        .limit(query.days)
    )
    rows = session.execute(stmt).all()

    points = [
        DiscoveryHistoryPoint(
            scanDate=r[0],
            discoveredCount=r[1],
            analyzedCount=r[2],
            qualifiedCount=r[3],
            suppressedCount=r[4],
            publishedCount=r[5],
        )
        for r in rows
    ]
    points.reverse()
    return points
