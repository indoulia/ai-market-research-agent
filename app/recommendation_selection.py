"""EPIC-M1.14: from all of one scan's M1.13-qualified candidates, deterministically
select the strongest positive opportunities -- ranked by the M1.9 opportunity score
-- while keeping every qualifying candidate auditable, selected or not. Does not
change consensus qualification (M1.8) or the score itself (M1.9); it only decides,
among already-qualifying candidates, which ones are selected.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Prediction,
    RecommendationGeneration,
    RecommendationSelection,
    ScanCandidate,
    Stock,
)
from .recommendation_generator import OUTCOME_QUALIFIED

SELECTION_VERSION = "RSL-001"

# Fixed product/policy constants, bumped via SELECTION_VERSION whenever changed.
MIN_SCORE_FOR_SELECTION = Decimal("50.00")
DEFAULT_DAILY_LIMIT = 5

REASON_SELECTED = "SELECTED"
REASON_BELOW_MIN_SCORE = "BELOW_MIN_SCORE"
REASON_DAILY_LIMIT_EXCEEDED = "DAILY_LIMIT_EXCEEDED"


@dataclass(frozen=True)
class RankedCandidate:
    generation: RecommendationGeneration
    prediction: Prediction
    symbol: str


def select_recommendations_for_scan(
    session: Session,
    scan_id: int,
    *,
    min_score: Decimal = MIN_SCORE_FOR_SELECTION,
    daily_limit: int = DEFAULT_DAILY_LIMIT,
) -> tuple[RecommendationSelection, ...]:
    """Idempotent: a scan that already has `RecommendationSelection` rows returns
    them unchanged rather than re-selecting, regardless of `min_score`/`daily_limit`
    passed on the re-run -- the first run's decision is the historical record."""
    existing = session.scalars(
        select(RecommendationSelection)
        .where(RecommendationSelection.scan_id == scan_id)
        .order_by(RecommendationSelection.id)
    ).all()
    if existing:
        return tuple(existing)

    ranked = _rank_qualifying_candidates(session, scan_id)

    selections: list[RecommendationSelection] = []
    rank = 0
    for candidate in ranked:
        if candidate.prediction.opportunity_score < min_score:
            reason = REASON_BELOW_MIN_SCORE
            assigned_rank = None
        else:
            rank += 1
            assigned_rank = rank
            reason = REASON_SELECTED if rank <= daily_limit else REASON_DAILY_LIMIT_EXCEEDED

        selections.append(
            RecommendationSelection(
                scan_id=scan_id,
                recommendation_generation_id=candidate.generation.id,
                rank=assigned_rank,
                selected=(reason == REASON_SELECTED),
                selection_reason=reason,
                selection_rule_version=SELECTION_VERSION,
            )
        )

    session.add_all(selections)
    session.commit()
    for selection in selections:
        session.refresh(selection)
    return tuple(selections)


def _rank_qualifying_candidates(session: Session, scan_id: int) -> list[RankedCandidate]:
    rows = session.execute(
        select(RecommendationGeneration, Prediction, Stock.symbol)
        .join(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
        .join(Prediction, Prediction.id == RecommendationGeneration.prediction_id)
        .join(Stock, Stock.id == Prediction.stock_id)
        .where(
            ScanCandidate.scan_id == scan_id,
            RecommendationGeneration.outcome == OUTCOME_QUALIFIED,
        )
    ).all()
    candidates = [RankedCandidate(generation=g, prediction=p, symbol=symbol) for g, p, symbol in rows]
    # Deterministic and repeatable: highest score first, ties broken by symbol ascending.
    candidates.sort(key=lambda c: (-c.prediction.opportunity_score, c.symbol))
    return candidates
