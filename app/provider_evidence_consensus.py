"""EPIC-M1.103: use independent provider/evidence agreement or
disagreement as an explicit signal of prediction reliability, data
quality and Trust Score, now that M1.91 gives this platform genuinely
independent second providers for fundamental and news/event data.

M1.65's own docstring noted that, at the time it was written, "a literal
fact-vs-fact contradiction between two evidence categories cannot
happen -- there is no second, independent source for the same fact."
That is no longer true for fundamental and news/event data since M1.91
added real second adapters (`alpha-vantage`, `finnhub`) alongside Yahoo
-- this module is the first to actually compare what two independent
providers reported about the *same* underlying fact.

**Market-data agreement is deliberately out of scope here**, honestly:
`MarketPrice` has a hard `(stock_id, timestamp)` uniqueness constraint
(M1.3) -- only one row can ever exist per day regardless of source, so
provider disagreement on a daily candle is resolved (deduped) at
ingestion time and is not observable from persisted history at all.

**Fundamental consensus** (`assess_fundamental_consensus`) compares each
distinct provider's most-recently-fetched `eps` for one `(stock_id,
period_end_date)` -- deduping to the latest `fetched_at` per source
first, so a source that was re-fetched multiple times never counts
more than once (AC: "duplicate sources do not falsely increase
consensus"). Each source's weight combines freshness (a fixed 3-tier
decay by `fetched_at` age) with M1.93's own per-provider reliability
verdict where measured, and a fixed `SOURCE_AUTHORITY_TIER` -- currently
`1` (equal) for every real provider in this platform, since none is
classified as a primary/regulatory source today; an honest, forward-
compatible constant, the same posture `PROVIDER_COST_PER_REQUEST_USD`
already takes.

**News/event consensus** (`classify_news_event_consensus`) distinguishes
independent corroboration from syndicated duplication the same way a
human editor would: two DIFFERENT providers reporting the exact same
normalized headline for the same `event_type` within a short window is
one syndicated wire story, not two independent confirmations; two
providers reporting genuinely different headlines in that window *is*
independent corroboration. Counting distinct normalized headlines,
not distinct source rows, is what keeps a re-syndicated story from
inflating the corroboration signal.

Every assessment is a propose-only, read-only signal (`trust_reduction_
recommended` on the fundamental side) with no write path to any
production/prediction table -- the same posture this platform's whole
family of drift/uncertainty/consensus EPICs (M1.101/M1.102) already
established.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FundamentalConsensusAssessment, FundamentalDataRecord, NewsConsensusAssessment, NewsEventRecord
from .provider_quality import ProviderQualityMetric, compute_provider_quality_report
from .refresh_policy import DATA_TYPE_FUNDAMENTAL

CONSENSUS_VERSION = "PEC-001"

METRIC_EPS = "EPS"

VERDICT_INSUFFICIENT_SOURCES = "INSUFFICIENT_SOURCES"
VERDICT_CONSENSUS_STRONG = "CONSENSUS_STRONG"
VERDICT_CONSENSUS_WEAK = "CONSENSUS_WEAK"
VERDICT_MATERIAL_DISAGREEMENT = "MATERIAL_DISAGREEMENT"

NEWS_VERDICT_SINGLE_SOURCE = "SINGLE_SOURCE"
NEWS_VERDICT_SYNDICATED_DUPLICATE = "SYNDICATED_DUPLICATE"
NEWS_VERDICT_INDEPENDENT_CORROBORATION = "INDEPENDENT_CORROBORATION"

# Fixed, documented, versioned policy constants -- not learned or fitted.
STRONG_AGREEMENT_THRESHOLD = Decimal("0.05")
MATERIAL_DISAGREEMENT_THRESHOLD = Decimal("0.20")

FRESHNESS_WEIGHT_RECENT = Decimal("1.0")
FRESHNESS_WEIGHT_STALE = Decimal("0.5")
FRESHNESS_WEIGHT_OLD = Decimal("0.25")
FRESHNESS_RECENT_WINDOW = timedelta(days=30)
FRESHNESS_STALE_WINDOW = timedelta(days=180)

# No provider in this platform is currently classified as a primary/
# regulatory source -- every real adapter is weighted equally until a
# future EPIC adds a genuinely higher-authority source.
SOURCE_AUTHORITY_TIER: dict[str, Decimal] = {
    "yahoo-finance": Decimal("1"),
    "alpha-vantage": Decimal("1"),
    "finnhub": Decimal("1"),
    "upstox-v3": Decimal("1"),
    "stooq": Decimal("1"),
}
DEFAULT_AUTHORITY_TIER = Decimal("1")

DEFAULT_SYNDICATION_WINDOW = timedelta(hours=6)


def _freshness_weight(fetched_at: datetime, evaluated_at: datetime) -> Decimal:
    age = evaluated_at.replace(tzinfo=None) - fetched_at.replace(tzinfo=None)
    if age <= FRESHNESS_RECENT_WINDOW:
        return FRESHNESS_WEIGHT_RECENT
    if age <= FRESHNESS_STALE_WINDOW:
        return FRESHNESS_WEIGHT_STALE
    return FRESHNESS_WEIGHT_OLD


def _reliability_weight(session: Session, source: str, *, computed_at: datetime) -> Decimal:
    report = compute_provider_quality_report(session, computed_at=computed_at)
    metric: ProviderQualityMetric | None = next(
        (m for m in report.by_provider if m.data_type == DATA_TYPE_FUNDAMENTAL and m.provider_id == source), None
    )
    if metric is None or metric.success_rate is None:
        # No measured reliability yet -- equal weight, never zero: an
        # unmeasured provider is not the same as an untrustworthy one.
        return Decimal("1")
    return metric.success_rate


def _latest_per_source(records: list[FundamentalDataRecord]) -> dict[str, FundamentalDataRecord]:
    latest: dict[str, FundamentalDataRecord] = {}
    for record in records:
        current = latest.get(record.source)
        if current is None or record.fetched_at > current.fetched_at:
            latest[record.source] = record
    return latest


def assess_fundamental_consensus(
    session: Session, *, stock_id: int, period_end_date: date, evaluated_at: datetime
) -> FundamentalConsensusAssessment:
    """Idempotent by `(stock_id, period_end_date, evaluated_at)`."""
    existing = session.scalar(
        select(FundamentalConsensusAssessment).where(
            FundamentalConsensusAssessment.stock_id == stock_id,
            FundamentalConsensusAssessment.period_end_date == period_end_date,
            FundamentalConsensusAssessment.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    records = list(
        session.scalars(
            select(FundamentalDataRecord).where(
                FundamentalDataRecord.stock_id == stock_id,
                FundamentalDataRecord.period_end_date == period_end_date,
                FundamentalDataRecord.eps.isnot(None),
            )
        ).all()
    )
    latest_per_source = _latest_per_source(records)
    sources_considered = sorted(latest_per_source)
    source_count = len(sources_considered)

    if source_count < 2:
        assessment = FundamentalConsensusAssessment(
            stock_id=stock_id, period_end_date=period_end_date, metric_name=METRIC_EPS, source_count=source_count,
            sources_considered=sources_considered, weighted_mean=None, max_relative_deviation=None,
            verdict=VERDICT_INSUFFICIENT_SOURCES, trust_reduction_recommended=False,
            evaluated_at=evaluated_at, consensus_rule_version=CONSENSUS_VERSION,
        )
    else:
        weights: dict[str, Decimal] = {}
        for source, record in latest_per_source.items():
            freshness = _freshness_weight(record.fetched_at, evaluated_at)
            reliability = _reliability_weight(session, source, computed_at=evaluated_at)
            authority = SOURCE_AUTHORITY_TIER.get(source, DEFAULT_AUTHORITY_TIER)
            weights[source] = freshness * reliability * authority

        total_weight = sum(weights.values())
        weighted_mean = (
            sum(latest_per_source[source].eps * weights[source] for source in sources_considered) / total_weight
            if total_weight > 0
            else None
        )

        if weighted_mean is None:
            max_relative_deviation = None
            verdict = VERDICT_INSUFFICIENT_SOURCES
        elif weighted_mean == 0:
            max_relative_deviation = None
            verdict = VERDICT_CONSENSUS_STRONG if all(latest_per_source[s].eps == 0 for s in sources_considered) else VERDICT_MATERIAL_DISAGREEMENT
        else:
            max_relative_deviation = max(
                abs(latest_per_source[source].eps - weighted_mean) / abs(weighted_mean) for source in sources_considered
            )
            if max_relative_deviation <= STRONG_AGREEMENT_THRESHOLD:
                verdict = VERDICT_CONSENSUS_STRONG
            elif max_relative_deviation >= MATERIAL_DISAGREEMENT_THRESHOLD:
                verdict = VERDICT_MATERIAL_DISAGREEMENT
            else:
                verdict = VERDICT_CONSENSUS_WEAK

        assessment = FundamentalConsensusAssessment(
            stock_id=stock_id, period_end_date=period_end_date, metric_name=METRIC_EPS, source_count=source_count,
            sources_considered=sources_considered, weighted_mean=weighted_mean,
            max_relative_deviation=max_relative_deviation, verdict=verdict,
            trust_reduction_recommended=(verdict == VERDICT_MATERIAL_DISAGREEMENT),
            evaluated_at=evaluated_at, consensus_rule_version=CONSENSUS_VERSION,
        )

    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_fundamental_consensus_history(session: Session, *, stock_id: int, period_end_date: date) -> tuple[FundamentalConsensusAssessment, ...]:
    return tuple(
        session.scalars(
            select(FundamentalConsensusAssessment)
            .where(FundamentalConsensusAssessment.stock_id == stock_id, FundamentalConsensusAssessment.period_end_date == period_end_date)
            .order_by(FundamentalConsensusAssessment.id.asc())
        ).all()
    )


def classify_news_event_consensus(
    session: Session,
    *,
    stock_id: int,
    event_type: str,
    anchor_published_at: datetime,
    evaluated_at: datetime,
    syndication_window: timedelta = DEFAULT_SYNDICATION_WINDOW,
) -> NewsConsensusAssessment:
    """Always computes and persists a fresh, independent assessment (the
    same "report" posture as M1.85/M1.99/M1.102) -- never mutates a
    prior classification for a different anchor timestamp."""
    naive_anchor = anchor_published_at.replace(tzinfo=None)
    window_start = naive_anchor - syndication_window
    window_end = naive_anchor + syndication_window

    records = list(
        session.scalars(
            select(NewsEventRecord).where(NewsEventRecord.stock_id == stock_id, NewsEventRecord.event_type == event_type)
        ).all()
    )
    in_window = [r for r in records if window_start <= r.published_at.replace(tzinfo=None) <= window_end]

    distinct_sources = {r.source for r in in_window}
    distinct_headlines = {r.headline.strip().casefold() for r in in_window}

    if len(distinct_sources) < 2:
        verdict = NEWS_VERDICT_SINGLE_SOURCE
    elif len(distinct_headlines) == 1:
        verdict = NEWS_VERDICT_SYNDICATED_DUPLICATE
    else:
        verdict = NEWS_VERDICT_INDEPENDENT_CORROBORATION

    assessment = NewsConsensusAssessment(
        stock_id=stock_id, event_type=event_type, anchor_published_at=anchor_published_at,
        distinct_source_count=len(distinct_sources), distinct_headline_count=len(distinct_headlines),
        record_count=len(in_window), verdict=verdict, evaluated_at=evaluated_at,
        consensus_rule_version=CONSENSUS_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_news_consensus_history(session: Session, *, stock_id: int, event_type: str) -> tuple[NewsConsensusAssessment, ...]:
    return tuple(
        session.scalars(
            select(NewsConsensusAssessment)
            .where(NewsConsensusAssessment.stock_id == stock_id, NewsConsensusAssessment.event_type == event_type)
            .order_by(NewsConsensusAssessment.id.asc())
        ).all()
    )
