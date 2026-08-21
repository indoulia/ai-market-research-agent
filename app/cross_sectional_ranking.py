"""EPIC-M1.99: rank one scan's qualified positive candidates against each
other (cross-sectionally, at the same point in time), and measure whether
that ranking is actually more effective than this platform's simpler,
already-production M1.14 opportunity-score-only selection.

`rank_scan_candidates` deliberately does not reimplement composite
scoring, concentration control, or snapshot persistence -- it is a thin
wrapper that resolves one scan's own M1.9-qualified candidates into
`prediction_id`s and hands them, unchanged, to M1.87's own
`rank_positive_opportunities`. Every scope item M1.99 shares with M1.87
("combine probability, expected return, risk, reward/risk, trust and
evidence quality," "penalize instability, concentration and weak
evidence," "preserve ranking snapshots") is satisfied by this
composition, not a second implementation -- avoiding the exact
vocabulary/logic-drift trap this platform has hit before when two
similarly-named EPICs each built their own version of the same idea.

`measure_ranking_effectiveness` is this EPIC's own, genuinely new
contribution: comparing the realized, already-evaluated success rate of
M1.87's composite-ranked top-K opportunities against M1.14's
`RecommendationSelection` opportunity-score-only top-K, over the same
already-resolved `PredictionOutcome` evidence -- never re-deriving either
ranking, never fabricating a benchmark. Below `MIN_SAMPLE_SIZE_FOR_
COMPARISON` on either side, the report is honestly `INSUFFICIENT_SAMPLE`,
never a false conclusion from a sparse comparison (the same posture
`out_of_sample_validation`/`prediction_attribution` already take).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Prediction,
    PredictionOutcome,
    PositiveOpportunityRanking,
    RankingEffectivenessReport,
    RecommendationGeneration,
    RecommendationSelection,
    ScanCandidate,
    Stock,
)
from .opportunity_ranking import rank_positive_opportunities
from .out_of_sample_validation import EvaluationWindow
from .recommendation_generator import OUTCOME_QUALIFIED
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

EFFECTIVENESS_RULE_VERSION = "CSR-001"

VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
VERDICT_COMPOSITE_BETTER = "COMPOSITE_BETTER"
VERDICT_ALTERNATIVE_BETTER = "ALTERNATIVE_BETTER"
VERDICT_NO_SIGNIFICANT_DIFFERENCE = "NO_SIGNIFICANT_DIFFERENCE"


def _qualified_prediction_ids_for_scan(session: Session, scan_id: int) -> list[int]:
    rows = session.execute(
        select(Prediction.id, Stock.symbol)
        .join(RecommendationGeneration, RecommendationGeneration.prediction_id == Prediction.id)
        .join(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
        .join(Stock, Stock.id == Prediction.stock_id)
        .where(ScanCandidate.scan_id == scan_id, RecommendationGeneration.outcome == OUTCOME_QUALIFIED)
        .order_by(Stock.symbol.asc())
    ).all()
    return [prediction_id for prediction_id, _symbol in rows]


def rank_scan_candidates(
    session: Session, scan_id: int, *, evaluated_at: datetime, horizon_days: int | None = None
) -> tuple[PositiveOpportunityRanking, ...]:
    """Cross-sectional ranking: this scan's own qualified candidates,
    ranked against each other via M1.87's unchanged composite ranking."""
    prediction_ids = _qualified_prediction_ids_for_scan(session, scan_id)
    return rank_positive_opportunities(session, prediction_ids, evaluated_at=evaluated_at, horizon_days=horizon_days)


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _composite_top_k_outcomes(session: Session, *, window: EvaluationWindow, top_k: int) -> list[str]:
    query = (
        select(PredictionOutcome.outcome)
        .join(PositiveOpportunityRanking, PositiveOpportunityRanking.prediction_id == PredictionOutcome.prediction_id)
        .where(
            PositiveOpportunityRanking.included.is_(True),
            PositiveOpportunityRanking.rank_position <= top_k,
            PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")),
        )
    )
    if window.start is not None:
        query = query.where(PositiveOpportunityRanking.evaluated_at >= window.start)
    if window.end is not None:
        query = query.where(PositiveOpportunityRanking.evaluated_at <= window.end)
    return list(session.scalars(query).all())


def _alternative_top_k_outcomes(session: Session, *, window: EvaluationWindow, top_k: int) -> list[str]:
    query = (
        select(PredictionOutcome.outcome)
        .select_from(RecommendationSelection)
        .join(RecommendationGeneration, RecommendationGeneration.id == RecommendationSelection.recommendation_generation_id)
        .join(Prediction, Prediction.id == RecommendationGeneration.prediction_id)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .where(
            RecommendationSelection.selected.is_(True),
            RecommendationSelection.rank <= top_k,
            PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")),
        )
    )
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    return list(session.scalars(query).all())


def measure_ranking_effectiveness(
    session: Session, *, window: EvaluationWindow, top_k: int, computed_at: datetime
) -> RankingEffectivenessReport:
    """Always computes and persists a fresh, independent report row (the
    same "report," not "per-entity decision," posture M1.85's
    `FactorAssociationReport` already takes) -- never mutates a prior
    measurement, and never declares a verdict without both sides clearing
    `MIN_SAMPLE_SIZE_FOR_COMPARISON` independently."""
    composite_outcomes = _composite_top_k_outcomes(session, window=window, top_k=top_k)
    alternative_outcomes = _alternative_top_k_outcomes(session, window=window, top_k=top_k)

    composite_sample_count = len(composite_outcomes)
    alternative_sample_count = len(alternative_outcomes)
    composite_success_count = sum(1 for o in composite_outcomes if o == "SUCCESS")
    alternative_success_count = sum(1 for o in alternative_outcomes if o == "SUCCESS")
    composite_success_rate = _rate(composite_success_count, composite_sample_count)
    alternative_success_rate = _rate(alternative_success_count, alternative_sample_count)

    if (
        composite_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or alternative_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
    ):
        verdict = VERDICT_INSUFFICIENT_SAMPLE
        success_rate_delta = None
    else:
        success_rate_delta = composite_success_rate - alternative_success_rate
        if success_rate_delta >= WEAKNESS_MARGIN:
            verdict = VERDICT_COMPOSITE_BETTER
        elif success_rate_delta <= -WEAKNESS_MARGIN:
            verdict = VERDICT_ALTERNATIVE_BETTER
        else:
            verdict = VERDICT_NO_SIGNIFICANT_DIFFERENCE

    report = RankingEffectivenessReport(
        window_label=window.label,
        top_k=top_k,
        composite_sample_count=composite_sample_count,
        composite_success_count=composite_success_count,
        composite_success_rate=composite_success_rate,
        alternative_sample_count=alternative_sample_count,
        alternative_success_count=alternative_success_count,
        alternative_success_rate=alternative_success_rate,
        success_rate_delta=success_rate_delta,
        verdict=verdict,
        computed_at=computed_at,
        effectiveness_rule_version=EFFECTIVENESS_RULE_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_effectiveness_report_history(session: Session) -> tuple[RankingEffectivenessReport, ...]:
    return tuple(session.scalars(select(RankingEffectivenessReport).order_by(RankingEffectivenessReport.id.asc())).all())
