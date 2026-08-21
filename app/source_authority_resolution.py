"""EPIC-M1.127: resolve conflicting external facts using explicit source
authority, freshness, provenance and fact-type policies -- never simple
provider majority voting.

**Architectural rule (from the EPIC doc): "Consensus is evidence;
authority is policy. They must never be conflated."** M1.103's
`app.provider_evidence_consensus` already characterizes *agreement* --
whether independent sources agree, and by how much -- and this module
deliberately does not duplicate that: it reuses `_latest_per_source`-
style deduplication on the same underlying evidence tables
(`FundamentalDataRecord`, `NewsEventRecord`) but adds a genuinely new
layer on top, an explicit per-fact-type authority POLICY
(`AUTHORITY_TIER_BY_FACT_TYPE`) that decides which single value is the
resolved fact, even when it disagrees with every other source (AC: "a
provider majority cannot automatically override a configured
authoritative source"). M1.103 computes a blended weighted mean across
all sources; this module instead picks a winner.

**Only two fact types have genuine multi-provider data on this platform
today** -- `FUNDAMENTAL_EPS` (M1.91 added `alpha-vantage`/`finnhub`
alongside `yahoo-finance`) and `NEWS_EVENT` (same three providers).
Corporate actions, filings and non-EPS financial-result fields are
honestly out of scope for this first version: `app.corporate_actions`
records each action from a single feed with no second, independent
source to ever conflict with, and price data has a hard
`(stock_id, timestamp)` uniqueness constraint that already resolves
(dedupes) provider disagreement at ingestion time, exactly the same
"deliberately out of scope, named not fabricated" posture
`provider_evidence_consensus` already took for market data.

**No provider is currently classified as a primary/regulatory source**
in `AUTHORITY_TIER_BY_FACT_TYPE` -- every real adapter is tier `1` today,
the same honest, forward-compatible stance M1.103's own
`SOURCE_AUTHORITY_TIER` already took (that dict is untouched by this
module; the two are intentionally decoupled per the architectural rule
above). When all available sources for a fact tie at the top tier, this
module falls back to **timestamp/effective-date precedence** (scope) --
the most-recently-fetched source wins -- rather than any consensus
blending.

**"Allow manual governance of authority rules without rewriting
historical facts"** (scope) is satisfied structurally: authority tiers
are a fixed, versioned Python policy table (this platform's established
convention for policy constants, e.g. `SECTOR_BENCHMARK_SYMBOLS`), not a
learned or DB-editable weight. Every `ResolvedFact` row freezes
`winning_source_authority_tier` and `resolution_rule_version` at
`resolved_at` -- a future change to `AUTHORITY_TIER_BY_FACT_TYPE` only
affects new resolutions under a new version string; old rows are
immutable and unaffected, the same frozen-row governance posture this
platform's whole EPIC family already established (M1.109's
`SectorRelativeAssessment`, M1.129's `BenchmarkRelativeAssessment`).

**Duplicated/syndicated evidence never inflates conflict detection**
(AC): two sources reporting the exact same normalized headline for a
news event are treated as agreeing (not as two independent facts to
reconcile), the same normalized-headline comparison
`provider_evidence_consensus.classify_news_event_consensus` already
uses for its own, distinct purpose (characterizing corroboration).

Propose-only: `ResolvedFact` has no write path into `Prediction`,
`PredictionTrustScore`, or any ranking table. "Fact-resolution output can
be consumed by prediction and learning systems" (AC) is satisfied by the
table being queryable, not by wiring it into any production decision
path yet -- the same posture M1.103/M1.109/M1.122/M1.129/M1.130 already
established, named here as explicit future work.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FundamentalDataRecord, NewsEventRecord, ResolvedFact

RESOLUTION_VERSION = "SAR-001"

FACT_TYPE_FUNDAMENTAL_EPS = "FUNDAMENTAL_EPS"
FACT_TYPE_NEWS_EVENT = "NEWS_EVENT"

REASON_INSUFFICIENT_SOURCES = "INSUFFICIENT_SOURCES"
REASON_SINGLE_SOURCE = "SINGLE_SOURCE"
REASON_NO_CONFLICT = "NO_CONFLICT"
REASON_AUTHORITATIVE_SOURCE_OVERRIDE = "AUTHORITATIVE_SOURCE_OVERRIDE"
REASON_TIMESTAMP_PRECEDENCE_TIEBREAK = "TIMESTAMP_PRECEDENCE_TIEBREAK"

# Fixed, documented, versioned policy constants -- not learned or fitted.
# No real provider is classified above tier 1 today; this is a forward-
# compatible seam for a future genuinely-authoritative source (e.g. an
# official exchange/regulatory filings feed), the same honest posture
# `provider_evidence_consensus.SOURCE_AUTHORITY_TIER` already took.
AUTHORITY_TIER_BY_FACT_TYPE: dict[str, dict[str, Decimal]] = {
    FACT_TYPE_FUNDAMENTAL_EPS: {"yahoo-finance": Decimal("1"), "alpha-vantage": Decimal("1"), "finnhub": Decimal("1")},
    FACT_TYPE_NEWS_EVENT: {"yahoo-finance": Decimal("1"), "alpha-vantage": Decimal("1"), "finnhub": Decimal("1")},
}
DEFAULT_AUTHORITY_TIER = Decimal("1")

CONFLICT_THRESHOLD = Decimal("0.20")
DEFAULT_SYNDICATION_WINDOW = timedelta(hours=6)

CONFIDENCE_INSUFFICIENT_SOURCES = Decimal("0")
CONFIDENCE_SINGLE_SOURCE = Decimal("0.5")
CONFIDENCE_NO_CONFLICT = Decimal("1.0")
CONFIDENCE_AUTHORITATIVE_OVERRIDE = Decimal("0.9")
CONFIDENCE_TIMESTAMP_TIEBREAK = Decimal("0.6")


def _authority_tier(fact_type: str, source: str) -> Decimal:
    return AUTHORITY_TIER_BY_FACT_TYPE.get(fact_type, {}).get(source, DEFAULT_AUTHORITY_TIER)


def _has_material_conflict(values: list[Decimal]) -> bool:
    if len(values) < 2:
        return False
    mean = sum(values) / Decimal(len(values))
    if mean == 0:
        return any(v != 0 for v in values)
    return max(abs(v - mean) / abs(mean) for v in values) >= CONFLICT_THRESHOLD


def _existing_resolution(session: Session, *, fact_type: str, stock_id: int, fact_key: str, resolved_at: datetime) -> ResolvedFact | None:
    return session.scalar(
        select(ResolvedFact).where(
            ResolvedFact.fact_type == fact_type, ResolvedFact.stock_id == stock_id,
            ResolvedFact.fact_key == fact_key, ResolvedFact.resolved_at == resolved_at,
        )
    )


def _persist(session: Session, resolved: ResolvedFact) -> ResolvedFact:
    session.add(resolved)
    session.commit()
    session.refresh(resolved)
    return resolved


def resolve_fundamental_fact(
    session: Session, *, stock_id: int, period_end_date, resolved_at: datetime,
) -> ResolvedFact:
    """Resolve the authoritative EPS for one `(stock_id, period_end_date)`.
    Idempotent by `(fact_type, stock_id, fact_key, resolved_at)`."""
    fact_key = period_end_date.isoformat()
    existing = _existing_resolution(session, fact_type=FACT_TYPE_FUNDAMENTAL_EPS, stock_id=stock_id, fact_key=fact_key, resolved_at=resolved_at)
    if existing is not None:
        return existing

    records = list(
        session.scalars(
            select(FundamentalDataRecord).where(
                FundamentalDataRecord.stock_id == stock_id, FundamentalDataRecord.period_end_date == period_end_date,
                FundamentalDataRecord.eps.isnot(None),
            )
        ).all()
    )
    latest_per_source: dict[str, FundamentalDataRecord] = {}
    for record in records:
        current = latest_per_source.get(record.source)
        if current is None or record.fetched_at > current.fetched_at:
            latest_per_source[record.source] = record
    sources = sorted(latest_per_source)

    if not sources:
        resolved = ResolvedFact(
            fact_type=FACT_TYPE_FUNDAMENTAL_EPS, stock_id=stock_id, fact_key=fact_key, resolved_value_numeric=None,
            resolved_value_text=None, winning_source=None, winning_source_authority_tier=None, source_count=0,
            sources_considered=[], conflicting=False, resolution_reason=REASON_INSUFFICIENT_SOURCES,
            confidence=CONFIDENCE_INSUFFICIENT_SOURCES, resolved_at=resolved_at, resolution_rule_version=RESOLUTION_VERSION,
        )
        return _persist(session, resolved)

    if len(sources) == 1:
        source = sources[0]
        resolved = ResolvedFact(
            fact_type=FACT_TYPE_FUNDAMENTAL_EPS, stock_id=stock_id, fact_key=fact_key,
            resolved_value_numeric=latest_per_source[source].eps, resolved_value_text=None, winning_source=source,
            winning_source_authority_tier=_authority_tier(FACT_TYPE_FUNDAMENTAL_EPS, source), source_count=1,
            sources_considered=sources, conflicting=False, resolution_reason=REASON_SINGLE_SOURCE,
            confidence=CONFIDENCE_SINGLE_SOURCE, resolved_at=resolved_at, resolution_rule_version=RESOLUTION_VERSION,
        )
        return _persist(session, resolved)

    tiers = {s: _authority_tier(FACT_TYPE_FUNDAMENTAL_EPS, s) for s in sources}
    max_tier = max(tiers.values())
    top_sources = [s for s in sources if tiers[s] == max_tier]
    conflicting = _has_material_conflict([latest_per_source[s].eps for s in sources])

    if not conflicting:
        winner = min(top_sources)
        reason, confidence = REASON_NO_CONFLICT, CONFIDENCE_NO_CONFLICT
    elif len(top_sources) == 1:
        winner = top_sources[0]
        reason, confidence = REASON_AUTHORITATIVE_SOURCE_OVERRIDE, CONFIDENCE_AUTHORITATIVE_OVERRIDE
    else:
        winner = max(top_sources, key=lambda s: latest_per_source[s].fetched_at)
        reason, confidence = REASON_TIMESTAMP_PRECEDENCE_TIEBREAK, CONFIDENCE_TIMESTAMP_TIEBREAK

    resolved = ResolvedFact(
        fact_type=FACT_TYPE_FUNDAMENTAL_EPS, stock_id=stock_id, fact_key=fact_key,
        resolved_value_numeric=latest_per_source[winner].eps, resolved_value_text=None, winning_source=winner,
        winning_source_authority_tier=tiers[winner], source_count=len(sources), sources_considered=sources,
        conflicting=conflicting, resolution_reason=reason, confidence=confidence, resolved_at=resolved_at,
        resolution_rule_version=RESOLUTION_VERSION,
    )
    return _persist(session, resolved)


def resolve_news_event_fact(
    session: Session, *, stock_id: int, event_type: str, anchor_published_at: datetime, resolved_at: datetime,
    syndication_window: timedelta = DEFAULT_SYNDICATION_WINDOW,
) -> ResolvedFact:
    """Resolve the canonical record for one news/event anchor. Idempotent
    by `(fact_type, stock_id, fact_key, resolved_at)`."""
    fact_key = f"{event_type}:{anchor_published_at.isoformat()}"
    existing = _existing_resolution(session, fact_type=FACT_TYPE_NEWS_EVENT, stock_id=stock_id, fact_key=fact_key, resolved_at=resolved_at)
    if existing is not None:
        return existing

    naive_anchor = anchor_published_at.replace(tzinfo=None)
    window_start = naive_anchor - syndication_window
    window_end = naive_anchor + syndication_window
    records = list(
        session.scalars(select(NewsEventRecord).where(NewsEventRecord.stock_id == stock_id, NewsEventRecord.event_type == event_type)).all()
    )
    in_window = [r for r in records if window_start <= r.published_at.replace(tzinfo=None) <= window_end]

    if not in_window:
        resolved = ResolvedFact(
            fact_type=FACT_TYPE_NEWS_EVENT, stock_id=stock_id, fact_key=fact_key, resolved_value_numeric=None,
            resolved_value_text=None, winning_source=None, winning_source_authority_tier=None, source_count=0,
            sources_considered=[], conflicting=False, resolution_reason=REASON_INSUFFICIENT_SOURCES,
            confidence=CONFIDENCE_INSUFFICIENT_SOURCES, resolved_at=resolved_at, resolution_rule_version=RESOLUTION_VERSION,
        )
        return _persist(session, resolved)

    distinct_sources = sorted({r.source for r in in_window})
    tiers = {s: _authority_tier(FACT_TYPE_NEWS_EVENT, s) for s in distinct_sources}
    max_tier = max(tiers.values())
    top_sources = {s for s in distinct_sources if tiers[s] == max_tier}
    top_records = [r for r in in_window if r.source in top_sources]
    # Conflict is judged across ALL sources, not just top-tier ones -- a
    # lone authoritative source must still be recognized as disagreeing
    # with the rest (AC: "a provider majority cannot automatically
    # override a configured authoritative source").
    distinct_headlines_all = {r.headline.strip().casefold() for r in in_window}
    conflicting = len(distinct_headlines_all) > 1

    if len(distinct_sources) == 1:
        reason, confidence = REASON_SINGLE_SOURCE, CONFIDENCE_SINGLE_SOURCE
    elif not conflicting:
        reason, confidence = REASON_NO_CONFLICT, CONFIDENCE_NO_CONFLICT
    elif len(top_sources) == 1:
        reason, confidence = REASON_AUTHORITATIVE_SOURCE_OVERRIDE, CONFIDENCE_AUTHORITATIVE_OVERRIDE
    else:
        reason, confidence = REASON_TIMESTAMP_PRECEDENCE_TIEBREAK, CONFIDENCE_TIMESTAMP_TIEBREAK

    winner_record = min(top_records, key=lambda r: r.published_at)
    resolved = ResolvedFact(
        fact_type=FACT_TYPE_NEWS_EVENT, stock_id=stock_id, fact_key=fact_key, resolved_value_numeric=None,
        resolved_value_text=winner_record.headline, winning_source=winner_record.source,
        winning_source_authority_tier=tiers[winner_record.source], source_count=len(distinct_sources),
        sources_considered=distinct_sources, conflicting=conflicting, resolution_reason=reason, confidence=confidence,
        resolved_at=resolved_at, resolution_rule_version=RESOLUTION_VERSION,
    )
    return _persist(session, resolved)


def get_resolved_fact_history(session: Session, *, fact_type: str, stock_id: int, fact_key: str) -> tuple[ResolvedFact, ...]:
    return tuple(
        session.scalars(
            select(ResolvedFact)
            .where(ResolvedFact.fact_type == fact_type, ResolvedFact.stock_id == stock_id, ResolvedFact.fact_key == fact_key)
            .order_by(ResolvedFact.id.asc())
        ).all()
    )
