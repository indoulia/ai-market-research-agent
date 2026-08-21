"""Query service backing the /api/v1/recommendations/{id} detail, history,
events and outcome contracts (EPIC-M1.137).

Composes existing, already-merged domain modules -- nothing recomputed:
  - M1.55 ``app.recommendation_revision`` for the active version and the
    revision chain (``getActiveVersion``/``getRevisionHistory``/
    ``compareVersions``).
  - M1.77/M1.16/M1.74 trust/confidence-quality/evidence-quality for
    ``trustScore``/``uncertainty``/``evidenceStrength``.
  - M1.66 ``RecommendationDecisionTrace`` for ``providerEvidence`` (the
    evidence categories considered at decision time).
  - M1.34 ``classify_liquidity_bucket`` for ``liquidity``.
  - M1.5 ``PredictionOutcome`` for ``/outcome``.
  - The M1.135 context-summary helpers for ``fundamental``/``news``/
    ``events``/``market``.

M1.105 (freshness/revision engine) merged after this EPIC's Dependencies
note was written; its ``PredictionFreshnessDecision`` rows are surfaced
in ``get_events`` as ``REANALYSIS_TRIGGER`` items alongside M1.54's
``EvidenceRevalidationCheck`` rows -- the two are distinct, non-
overlapping signals (evidence-staleness-per-category vs. prediction-
level drift/disagreement/material-change) and both belong on this feed.

M1.119 (real-time outcome monitor) and M1.126 (information latency) are
still APPROVED but not yet implemented. M1.129 (benchmark-relative alpha)
landed after this EPIC's Dependencies note was written --
``benchmarkRelative``/``benchmarkReturnPct`` now read the latest
BROAD_MARKET-level ``app.benchmark_relative_alpha.BenchmarkRelativeAssessment``
row when one exists (``None`` until that assessment has actually been
computed for a prediction -- this module never computes it on the fly).
Consequences, named rather than hidden:
  - Outcome detection reflects M1.5's periodic (lifecycle-check-time)
    evaluation, not true real-time detection latency.
  - ``expiryAt`` is a naive calendar-day estimate
    (``asOf + horizonDays`` days), not trading-day/market-calendar-aware,
    since M1.121 (market calendar) hasn't landed.

History/events pagination uses a plain offset cursor
(`api/pagination.py::encode_offset_cursor`), not full keyset pagination:
each is a small, effectively-immutable, single-recommendation-scoped
sequence, not a large live-ranked feed, so "stable during a query
session" holds without keyset machinery.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.benchmark_relative_alpha import LEVEL_BROAD_MARKET, get_benchmark_relative_history
from app.confidence_quality import get_confidence_quality
from app.decision_trace import get_decision_trace
from app.discovery_segmentation import BUCKET_UNCLASSIFIED, classify_liquidity_bucket
from app.evidence_quality_gate import get_quality_decision_history
from app.models import (
    CorporateAction,
    EvidenceRevalidationCheck,
    NewsEventRecord,
    Prediction,
    PositiveOpportunityRanking,
    PredictionOutcome,
    RecommendationGeneration,
    RecommendationLifecycle,
    ScanCandidate,
    Stock,
)
from app.opportunity_ranking import OPPORTUNITY_RANKING_VERSION
from app.prediction_freshness_engine import get_freshness_history
from app.prediction_trust_score import get_trust_score_history
from app.recommendation_revision import compare_versions, get_active_version, get_revision_history
from app.target_stop_loss import TARGET_STOP_METHODOLOGY_VERSION, get_publication

from ..errors import NotFoundError
from ..pagination import DEFAULT_PAGE_SIZE, decode_offset_cursor, encode_offset_cursor
from ..schemas.recommendations import PredictionVersions
from ..schemas.recommendation_detail import (
    EVENT_TYPE_CORPORATE_ACTION,
    EVENT_TYPE_NEWS,
    EVENT_TYPE_REANALYSIS_TRIGGER,
    OUTCOME_STATUS_PENDING,
    TIMELINE_REASON_INITIAL_PREDICTION,
    EventItem,
    EvidenceResponse,
    HistoryItem,
    OutcomeResponse,
    RecommendationDetail,
    TimelineItem,
)
from .context_summaries import (
    event_summary,
    evidence_freshness,
    fundamental_summary,
    latest_market_price_pair,
    market_summary,
    news_summary,
)


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _resolve_generation(session: Session, recommendation_id: int) -> RecommendationGeneration:
    generation = session.get(RecommendationGeneration, recommendation_id)
    if generation is None or generation.prediction_id is None:
        raise NotFoundError("Recommendation", str(recommendation_id))
    return generation


def _latest_ranking_score(session: Session, prediction_id: int) -> Decimal | None:
    row = session.scalar(
        select(PositiveOpportunityRanking)
        .where(PositiveOpportunityRanking.prediction_id == prediction_id, PositiveOpportunityRanking.included.is_(True))
        .order_by(PositiveOpportunityRanking.evaluated_at.desc())
        .limit(1)
    )
    return row.composite_score if row is not None else None


def _latest_trust(session: Session, prediction_id: int) -> Decimal | None:
    history = get_trust_score_history(session, prediction_id)
    return history[-1].overall_trust_score if history else None


def _latest_broad_market_assessment(session: Session, prediction_id: int):
    broad_market_history = [a for a in get_benchmark_relative_history(session, prediction_id) if a.benchmark_level == LEVEL_BROAD_MARKET]
    return broad_market_history[-1] if broad_market_history else None


def _benchmark_relative_summary(assessment) -> str | None:
    if assessment is None:
        return None
    return f"{assessment.verdict} vs {assessment.benchmark_code} (alpha {assessment.relative_alpha})"


def _target_stop_upside(session: Session, prediction: Prediction) -> tuple[Decimal, Decimal, Decimal]:
    publication = get_publication(session, prediction.id, methodology_version=TARGET_STOP_METHODOLOGY_VERSION)
    target_price = publication.target_price if publication else prediction.entry_price * (1 + prediction.target_return)
    stop_loss = publication.stop_loss_price if publication else prediction.entry_price * (1 + prediction.stop_return)
    upside_pct = publication.upside_percentage if publication else prediction.target_return * 100
    return target_price, stop_loss, upside_pct


def get_detail(session: Session, recommendation_id: int) -> RecommendationDetail:
    generation = _resolve_generation(session, recommendation_id)
    original = session.get(Prediction, generation.prediction_id)
    active = get_active_version(session, original)
    stock = session.get(Stock, active.stock_id)
    scan_candidate = session.scalar(select(ScanCandidate).where(ScanCandidate.id == generation.scan_candidate_id))
    lifecycle = session.scalar(
        select(RecommendationLifecycle).where(RecommendationLifecycle.recommendation_generation_id == generation.id)
    )
    target_price, stop_loss, upside_pct = _target_stop_upside(session, active)
    current_price, _ = latest_market_price_pair(session, active.stock_id)
    evidence_history = get_quality_decision_history(session, active.id)
    evidence_decision = evidence_history[-1] if evidence_history else None
    confidence_quality = get_confidence_quality(session, active.id)
    decision_trace = get_decision_trace(session, generation.id)
    liquidity = classify_liquidity_bucket(scan_candidate.volume_ratio_20d) if scan_candidate else BUCKET_UNCLASSIFIED
    technical = (
        f"SMA20 distance {scan_candidate.sma20_distance}, volume ratio {scan_candidate.volume_ratio_20d}, ATR% {scan_candidate.atr_percent}"
        if scan_candidate is not None
        else None
    )

    return RecommendationDetail(
        id=generation.id,
        symbol=stock.symbol,
        exchange=stock.exchange,
        companyName=stock.company_name,
        predictionVersion=_prediction_versions(active),
        createdAt=generation.created_at,
        updatedAt=(lifecycle.last_checked_at if lifecycle and lifecycle.last_checked_at else (lifecycle.created_at if lifecycle else generation.created_at)),
        asOf=active.as_of_timestamp,
        entryPrice=active.entry_price,
        currentPrice=current_price,
        targetPrice=target_price,
        stopLoss=stop_loss,
        horizonDays=active.horizon_days,
        expiryAt=active.as_of_timestamp + timedelta(days=active.horizon_days),
        upsidePct=upside_pct,
        probability=active.predicted_probability,
        score=_latest_ranking_score(session, active.id),
        confidence=active.confidence,
        trustScore=_latest_trust(session, active.id),
        uncertainty=confidence_quality.quality if confidence_quality else None,
        evidenceStrength=evidence_decision.state if evidence_decision else None,
        fundamental=fundamental_summary(session, active.stock_id),
        technical=technical,
        market=market_summary(session, scan_candidate.scan_id if scan_candidate else None),
        news=news_summary(session, active.stock_id),
        events=event_summary(session, active.stock_id),
        benchmarkRelative=_benchmark_relative_summary(_latest_broad_market_assessment(session, active.id)),
        liquidity=liquidity,
        providerEvidence=list(decision_trace.evidence_categories_snapshot) if decision_trace else [],
        status=lifecycle.state if lifecycle else active.status,
        evidenceFreshness=evidence_freshness(session, active.id),
    )


def _prediction_versions(prediction: Prediction) -> PredictionVersions:
    return PredictionVersions(
        modelVersion=prediction.model_version,
        featureVersion=prediction.feature_version,
        consensusContractVersion=prediction.consensus_contract_version,
        horizonSelectionVersion=prediction.horizon_selection_version,
        scoringContractVersion=prediction.scoring_contract_version,
        rankingVersion=OPPORTUNITY_RANKING_VERSION,
    )


@dataclass
class HistoryPage:
    items: list[HistoryItem]
    next_cursor: str | None


def _change_summary(comparison) -> str:
    parts = [
        f"score {comparison.opportunity_score_delta:+.2f}",
        f"confidence {comparison.confidence_delta:+.4f}",
        f"target {comparison.target_return_delta:+.4f}",
    ]
    if comparison.horizon_changed:
        parts.append(f"horizon {comparison.previous_horizon_days}d->{comparison.revised_horizon_days}d")
    return ", ".join(parts)


def get_history(session: Session, recommendation_id: int, *, from_ts=None, to_ts=None, cursor: str | None = None, page_size: int = DEFAULT_PAGE_SIZE) -> HistoryPage:
    generation = _resolve_generation(session, recommendation_id)
    revisions = get_revision_history(session, generation.prediction_id)
    # SQLite drops tzinfo on DateTime(timezone=True) round-trip, so
    # `revision.revised_at` may come back naive while `from_ts`/`to_ts`
    # (parsed from a query param that always carries an offset) are aware.
    # Normalize both sides to aware UTC before comparing.
    from_ts = _as_aware_utc(from_ts)
    to_ts = _as_aware_utc(to_ts)
    filtered = [
        r for r in revisions
        if (from_ts is None or _as_aware_utc(r.revised_at) >= from_ts)
        and (to_ts is None or _as_aware_utc(r.revised_at) <= to_ts)
    ]

    offset = decode_offset_cursor(cursor) if cursor else 0
    page = filtered[offset : offset + page_size]

    items = []
    for revision in page:
        comparison = compare_versions(session, revision)
        revised = session.get(Prediction, revision.revised_prediction_id)
        target_price, stop_loss, _upside = _target_stop_upside(session, revised)
        items.append(
            HistoryItem(
                timestamp=revision.revised_at,
                version=revision.version_number,
                price=revised.entry_price,
                targetPrice=target_price,
                stopLoss=stop_loss,
                probability=revised.predicted_probability,
                score=_latest_ranking_score(session, revised.id),
                confidence=revised.confidence,
                trustScore=_latest_trust(session, revised.id),
                triggerType=revision.revision_reason,
                triggerEventId=revision.triggering_evidence_revalidation_check_id,
                changeSummary=_change_summary(comparison),
            )
        )

    next_cursor = encode_offset_cursor(offset + page_size) if offset + page_size < len(filtered) else None
    return HistoryPage(items=items, next_cursor=next_cursor)


def _affected_metrics(session: Session, comparison, previous_prediction_id: int, revised_prediction_id: int) -> list[str]:
    """Which specific metrics a revision actually moved -- lets the UI
    answer "why did target/SL/confidence/Trust change" (M3.4 AC) without
    re-deriving deltas itself from raw before/after values."""
    metrics: list[str] = []
    if comparison.opportunity_score_delta != 0:
        metrics.append("score")
    if comparison.confidence_delta != 0:
        metrics.append("confidence")
    if comparison.predicted_probability_delta != 0:
        metrics.append("probability")
    if comparison.target_return_delta != 0:
        metrics.append("targetPrice")
    if comparison.stop_return_delta != 0:
        metrics.append("stopLoss")
    if comparison.horizon_changed:
        metrics.append("horizonDays")
    if _latest_trust(session, previous_prediction_id) != _latest_trust(session, revised_prediction_id):
        metrics.append("trustScore")
    return metrics


def get_timeline(session: Session, recommendation_id: int) -> list[TimelineItem]:
    """EPIC-M3.4: the full, ordered prediction-version timeline. Unlike
    `/history` (paginated, revisions-only), this always starts with
    version 1 -- the original prediction, which is never itself a
    `RecommendationRevision` row -- so a caller can reconstruct the whole
    lifecycle (AC: "reconstruct why target/SL/confidence/Trust changed")
    from one call. Small and bounded (a recommendation is rarely revised
    more than a handful of times), so unlike `/history`/`/events` this is
    not cursor-paginated."""
    generation = _resolve_generation(session, recommendation_id)
    original = session.get(Prediction, generation.prediction_id)
    revisions = get_revision_history(session, generation.prediction_id)

    target_price, stop_loss, _upside = _target_stop_upside(session, original)
    items = [
        TimelineItem(
            version=1,
            timestamp=generation.created_at,
            reason=TIMELINE_REASON_INITIAL_PREDICTION,
            changeSummary="Initial prediction.",
            affectedMetrics=[],
            price=original.entry_price,
            targetPrice=target_price,
            stopLoss=stop_loss,
            probability=original.predicted_probability,
            score=_latest_ranking_score(session, original.id),
            confidence=original.confidence,
            trustScore=_latest_trust(session, original.id),
        )
    ]
    for revision in revisions:
        comparison = compare_versions(session, revision)
        revised = session.get(Prediction, revision.revised_prediction_id)
        target_price, stop_loss, _upside = _target_stop_upside(session, revised)
        items.append(
            TimelineItem(
                version=revision.version_number,
                timestamp=revision.revised_at,
                reason=revision.revision_reason,
                changeSummary=_change_summary(comparison),
                affectedMetrics=_affected_metrics(
                    session, comparison, revision.previous_prediction_id, revision.revised_prediction_id
                ),
                price=revised.entry_price,
                targetPrice=target_price,
                stopLoss=stop_loss,
                probability=revised.predicted_probability,
                score=_latest_ranking_score(session, revised.id),
                confidence=revised.confidence,
                trustScore=_latest_trust(session, revised.id),
            )
        )
    return items


def get_evidence(session: Session, recommendation_id: int) -> EvidenceResponse:
    """EPIC-M3.4: the evidence/provenance subset of `/{id}`'s detail
    payload, as its own contract. Delegates to `get_detail` rather than
    re-querying, so this is always exactly consistent with what the
    detail endpoint shows -- never a second, independently-computed
    source of truth for the same evidence fields."""
    detail = get_detail(session, recommendation_id)
    return EvidenceResponse(
        fundamental=detail.fundamental,
        technical=detail.technical,
        market=detail.market,
        news=detail.news,
        events=detail.events,
        evidenceStrength=detail.evidenceStrength,
        liquidity=detail.liquidity,
        providerEvidence=detail.providerEvidence,
    )


@dataclass
class EventsPage:
    items: list[EventItem]
    next_cursor: str | None


def get_events(session: Session, recommendation_id: int, *, cursor: str | None = None, page_size: int = DEFAULT_PAGE_SIZE) -> EventsPage:
    generation = _resolve_generation(session, recommendation_id)
    prediction = session.get(Prediction, generation.prediction_id)
    stock_id = prediction.stock_id

    news = session.scalars(select(NewsEventRecord).where(NewsEventRecord.stock_id == stock_id)).all()
    actions = session.scalars(select(CorporateAction).where(CorporateAction.stock_id == stock_id)).all()
    reanalysis = session.scalars(
        select(EvidenceRevalidationCheck).where(
            EvidenceRevalidationCheck.prediction_id == prediction.id,
            EvidenceRevalidationCheck.revalidation_required.is_(True),
        )
    ).all()
    freshness_decisions = [d for d in get_freshness_history(session, prediction.id) if d.re_analysis_recommended]

    merged: list[EventItem] = []
    for record in news:
        merged.append(EventItem(timestamp=record.published_at, eventType=EVENT_TYPE_NEWS, description=record.headline, materiality=record.materiality))
    for record in actions:
        merged.append(EventItem(
            timestamp=record.recorded_at, eventType=EVENT_TYPE_CORPORATE_ACTION,
            description=f"{record.action_type} effective {record.effective_date.isoformat()}", materiality=None,
        ))
    for record in reanalysis:
        merged.append(EventItem(
            timestamp=record.checked_at, eventType=EVENT_TYPE_REANALYSIS_TRIGGER,
            description=f"{record.evidence_category} revalidation required ({record.reason or 'unspecified'})", materiality=None,
        ))
    for decision in freshness_decisions:
        trigger_names = ", ".join(t["trigger"] for t in decision.triggers) or "unspecified"
        merged.append(EventItem(
            timestamp=decision.evaluated_at, eventType=EVENT_TYPE_REANALYSIS_TRIGGER,
            description=f"Freshness engine: {trigger_names}", materiality=None,
        ))
    merged.sort(key=lambda item: item.timestamp, reverse=True)

    offset = decode_offset_cursor(cursor) if cursor else 0
    page = merged[offset : offset + page_size]
    next_cursor = encode_offset_cursor(offset + page_size) if offset + page_size < len(merged) else None
    return EventsPage(items=page, next_cursor=next_cursor)


def get_outcome(session: Session, recommendation_id: int) -> OutcomeResponse:
    generation = _resolve_generation(session, recommendation_id)
    original = session.get(Prediction, generation.prediction_id)
    active = get_active_version(session, original)
    outcome = session.scalar(select(PredictionOutcome).where(PredictionOutcome.prediction_id == active.id))
    if outcome is None:
        return OutcomeResponse(
            status=OUTCOME_STATUS_PENDING, detectedAt=None, observedPrice=None, realizedReturnPct=None,
            targetHit=None, stopLossHit=None, horizonExpired=None, benchmarkReturnPct=None, evidenceId=None,
        )
    horizon_expired = outcome.outcome != "UNEVALUABLE" and not outcome.target_hit and not outcome.stop_hit
    broad_market_assessment = _latest_broad_market_assessment(session, active.id)
    return OutcomeResponse(
        status=outcome.outcome,
        detectedAt=outcome.evaluation_date,
        observedPrice=outcome.closing_price,
        realizedReturnPct=outcome.actual_return * 100,
        targetHit=outcome.target_hit,
        stopLossHit=outcome.stop_hit,
        horizonExpired=horizon_expired,
        benchmarkReturnPct=(
            broad_market_assessment.benchmark_return_pct * 100
            if broad_market_assessment is not None and broad_market_assessment.benchmark_return_pct is not None
            else None
        ),
        evidenceId=outcome.id,
    )
