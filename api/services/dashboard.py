"""Query service backing GET /api/v1/dashboard/snapshot (EPIC-M3.2).

Composes existing, already-merged query services -- nothing recomputed:
  - M1.135 ``list_recommendations`` for ``topOpportunities`` (sort=score
    desc) and ``recentChanges`` (sort=updatedAt desc, i.e. the
    recommendations whose lifecycle was most recently (re-)checked --
    there is no dedicated lifecycle-transition-history table anywhere in
    this platform, so "recently changed" is honestly the same open,
    positive-only feed M1.135 already serves, just ordered by recency of
    update rather than score. No new business/ranking logic.
  - M1.139 ``get_market_summary`` for ``marketStatus``/``marketRegime``/
    ``indices``/``asOf`` (same honest gaps: `marketStatus` is always
    `MARKET_STATUS_UNKNOWN`, `indices` is always `[]` -- no
    market-calendar or index-feed module exists yet).
  - M1.139 ``list_news``/``list_events`` for ``importantEvents`` -- merged
    into one time-ordered feed the same way the M1.140 Flutter UI already
    merges them client-side, done once here so the dashboard needs only
    one request for its events strip.
  - M1.147 ``get_summary`` (fixed 30d window) for ``trustSummary``.

Only positive-eligible, open-lifecycle recommendations ever appear in
``topOpportunities``/``recentChanges`` -- inherited unchanged from
M1.135's own product constraint (no negative/cautious recommendations in
the user-facing feed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..schemas.dashboard import (
    DASHBOARD_EVENT_CORPORATE_ACTION,
    DASHBOARD_EVENT_NEWS,
    DashboardEvent,
    DashboardOpportunity,
    DashboardSnapshot,
    DashboardTrustSummary,
    DataFreshness,
)
from ..schemas.recommendations import RecommendationSummary
from .market import get_market_summary
from .news_events import FeedQuery, list_events, list_news
from .recommendations import RecommendationQuery, list_recommendations
from .tracking import get_summary as get_tracking_summary

TRUST_SUMMARY_RANGE = "30d"
DASHBOARD_DEFAULT_LIMIT = 10
DASHBOARD_MAX_LIMIT = 50


def _as_aware_utc(value: datetime) -> datetime:
    # SQLite drops tzinfo on DateTime(timezone=True) round-trip (same class
    # of bug already fixed in api/services/tracking.py); normalize before
    # any Python-side comparison/sort across sources.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@dataclass
class DashboardQuery:
    market: str | None = None
    horizon: int | None = None
    limit: int = DASHBOARD_DEFAULT_LIMIT
    # `sector`/`marketCapBucket` are not in EPIC-M3.2's own minimal
    # "Query: market, horizon, limit" list, but the UI Scope separately
    # requires "quick filters for horizon, market, sector and size" -- so
    # these are additive, optional filters reusing M1.135's exact existing
    # `sector`/`marketCapBucket` vocabulary, not a new filter contract.
    sector: str | None = None
    market_cap_bucket: str | None = None


def _to_opportunity(item: RecommendationSummary) -> DashboardOpportunity:
    # `companyName` is nullable on the underlying recommendation (a symbol
    # can lack one); falling back to the symbol itself is an honest
    # "best available label", never a fabricated company name.
    return DashboardOpportunity(
        id=item.id,
        symbol=item.symbol,
        name=item.companyName or item.symbol,
        price=item.price,
        targetPrice=item.targetPrice,
        stopLoss=item.stopLoss,
        horizon=item.horizonDays,
        upsidePercent=item.upsidePct,
        score=item.score,
        confidence=item.confidence,
        trustScore=item.trustScore,
        status=item.status,
        updatedAt=item.updatedAt,
    )


def get_dashboard_snapshot(session: Session, query: DashboardQuery) -> DashboardSnapshot:
    market_summary = get_market_summary(session)

    top_page = list_recommendations(
        session,
        RecommendationQuery(
            horizon=query.horizon,
            market=query.market,
            sector=query.sector,
            market_cap_bucket=query.market_cap_bucket,
            sort="score",
            direction="desc",
            page_size=query.limit,
        ),
    )
    top_opportunities = [_to_opportunity(item) for item in top_page.items]

    changes_page = list_recommendations(
        session,
        RecommendationQuery(
            horizon=query.horizon,
            market=query.market,
            sector=query.sector,
            market_cap_bucket=query.market_cap_bucket,
            sort="updatedAt",
            direction="desc",
            page_size=query.limit,
        ),
    )
    recent_changes = [_to_opportunity(item) for item in changes_page.items]

    news_page = list_news(session, FeedQuery(page_size=query.limit))
    events_page = list_events(session, FeedQuery(page_size=query.limit))

    merged_events: list[DashboardEvent] = [
        DashboardEvent(
            kind=DASHBOARD_EVENT_NEWS,
            symbol=n.symbol,
            title=n.headline,
            occurredAt=n.publishedAt,
            source=n.source,
            materiality=n.materiality,
            evidenceId=n.evidenceId,
        )
        for n in news_page.items
    ] + [
        DashboardEvent(
            kind=DASHBOARD_EVENT_CORPORATE_ACTION,
            symbol=e.symbol,
            title=e.title,
            occurredAt=e.effectiveAt,
            source=e.source,
            materiality=e.materiality,
            evidenceId=e.evidenceId,
        )
        for e in events_page.items
    ]
    merged_events.sort(key=lambda e: _as_aware_utc(e.occurredAt), reverse=True)
    important_events = merged_events[: query.limit]

    tracking_summary = get_tracking_summary(session, TRUST_SUMMARY_RANGE)
    trust_summary = DashboardTrustSummary(
        trustScore=tracking_summary.trustScore,
        trustDelta=tracking_summary.trustDelta,
        calibrationScore=tracking_summary.calibrationScore,
        sampleSize=tracking_summary.closedCount,
        smallSample=tracking_summary.smallSample,
        modelVersion=tracking_summary.modelVersion,
    )

    opportunities_as_of: datetime | None = max((_as_aware_utc(o.updatedAt) for o in top_opportunities), default=None)
    news_as_of: datetime | None = max((_as_aware_utc(e.occurredAt) for e in important_events), default=None)

    return DashboardSnapshot(
        marketStatus=market_summary.marketStatus,
        asOf=market_summary.asOf,
        marketRegime=market_summary.regime,
        indices=market_summary.indexes,
        topOpportunities=top_opportunities,
        importantEvents=important_events,
        recentChanges=recent_changes,
        trustSummary=trust_summary,
        dataFreshness=DataFreshness(
            opportunitiesAsOf=opportunities_as_of,
            marketAsOf=market_summary.asOf,
            newsAsOf=news_as_of,
        ),
    )
