"""EPIC-M1.13: convert a single M1.12 scan candidate into a positive recommendation
when every required positive gate (M1.8 consensus, M1.9 score, M1.10 horizon) is
satisfied, or an explicit non-qualification record otherwise -- never a negative
recommendation. This is the first point in the pipeline where consensus, score, and
horizon are all required together, since `record_recommendation` (app/recommendations.py)
requires all three contract versions on every row.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .consensus import ConsensusInputs, evaluate_positive_consensus
from .horizon import record_recommendation_with_selected_horizon
from .models import Prediction, RecommendationGeneration, ScanCandidate
from .scoring import ScoringInputs, compute_positive_opportunity_score

GENERATOR_VERSION = "PRG-001"

OUTCOME_QUALIFIED = "QUALIFIED"
OUTCOME_NOT_QUALIFIED = "NOT_QUALIFIED"

IMMUTABLE_FIELDS = (
    "scan_candidate_id",
    "outcome",
    "consensus_contract_version",
    "failed_criteria",
    "prediction_id",
    "created_at",
)


class RecommendationGenerationImmutableError(RuntimeError):
    pass


@event.listens_for(RecommendationGeneration, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise RecommendationGenerationImmutableError(
            f"recommendation generation {target.id} field(s) {changed} cannot be modified after creation"
        )


class CandidateNotEligibleError(RuntimeError):
    pass


def generate_recommendation_for_candidate(
    session: Session,
    scan_candidate: ScanCandidate,
    *,
    as_of_timestamp: datetime,
    entry_price: Decimal,
    target_return: Decimal,
    stop_return: Decimal,
) -> RecommendationGeneration:
    """Idempotent: a `scan_candidate` that already has a `RecommendationGeneration`
    row returns it unchanged rather than generating (or evaluating) again. Raises
    `CandidateNotEligibleError` for a candidate the scan already excluded -- there is
    no signal to qualify or score for one."""
    existing = session.scalar(
        select(RecommendationGeneration).where(
            RecommendationGeneration.scan_candidate_id == scan_candidate.id
        )
    )
    if existing is not None:
        return existing

    if not scan_candidate.eligible:
        raise CandidateNotEligibleError(
            f"scan candidate {scan_candidate.id} was excluded by the scan "
            f"({scan_candidate.exclusion_reason}); nothing to generate"
        )

    consensus = evaluate_positive_consensus(
        ConsensusInputs(
            predicted_probability=scan_candidate.predicted_probability,
            confidence=scan_candidate.confidence,
            sma20_distance=scan_candidate.sma20_distance,
            volume_ratio_20d=scan_candidate.volume_ratio_20d,
            data_quality_passed=scan_candidate.data_quality_passed,
        )
    )

    if not consensus.qualifies:
        generation = RecommendationGeneration(
            scan_candidate_id=scan_candidate.id,
            outcome=OUTCOME_NOT_QUALIFIED,
            consensus_contract_version=consensus.contract_version,
            failed_criteria=[c.name for c in consensus.failed_criteria()],
            prediction_id=None,
        )
        session.add(generation)
        session.commit()
        session.refresh(generation)
        return generation

    score = compute_positive_opportunity_score(
        ScoringInputs(
            predicted_probability=scan_candidate.predicted_probability,
            confidence=scan_candidate.confidence,
            sma20_distance=scan_candidate.sma20_distance,
            volume_ratio_20d=scan_candidate.volume_ratio_20d,
        )
    )

    recommendation: Prediction = record_recommendation_with_selected_horizon(
        session,
        consensus,
        scan_candidate.atr_percent,
        stock_id=scan_candidate.stock_id,
        as_of_timestamp=as_of_timestamp,
        entry_price=entry_price,
        target_return=target_return,
        stop_return=stop_return,
        predicted_probability=scan_candidate.predicted_probability,
        confidence=scan_candidate.confidence,
        model_version=scan_candidate.model_version,
        feature_version=scan_candidate.feature_version,
        scoring_contract_version=score.contract_version,
        opportunity_score=score.total_score,
    )

    generation = RecommendationGeneration(
        scan_candidate_id=scan_candidate.id,
        outcome=OUTCOME_QUALIFIED,
        consensus_contract_version=consensus.contract_version,
        failed_criteria=None,
        prediction_id=recommendation.id,
    )
    session.add(generation)
    session.commit()
    session.refresh(generation)
    return generation
