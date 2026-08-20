"""EPIC-M1.9: a transparent, versioned, deterministic score that ranks stocks which
already pass the EPIC-M1.8 positive-consensus gate. Does not change the gate itself,
train any model, or optimize weights from historical outcomes (all non-goals) -- every
weight and saturation ceiling below is a fixed, documented product/policy constant,
bumped via CONTRACT_VERSION whenever changed.

Scores the same "approved positive signals" the consensus gate already uses
(app/consensus.py), normalized so no single metric can dominate the total by accident.
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from .consensus import (
    MIN_CONFIDENCE,
    MIN_PREDICTED_PROBABILITY,
    MIN_VOLUME_RATIO_20D,
    ConsensusEvaluation,
    ConsensusNotQualifiedError,
)
from .models import Prediction
from .recommendations import record_recommendation

CONTRACT_VERSION = "POS-001"

# Saturation range each component is normalized over: `floor` maps to a 0 contribution,
# `ceiling` maps to the component's full weight. Reusing the consensus gate's own
# floors keeps scoring consistent with what "qualifying" already means.
PROBABILITY_FLOOR = MIN_PREDICTED_PROBABILITY
PROBABILITY_CEILING = Decimal("1.00")
CONFIDENCE_FLOOR = MIN_CONFIDENCE
CONFIDENCE_CEILING = Decimal("1.00")
TREND_CEILING = Decimal("0.10")  # +10% above the 20-day SMA is treated as maximally strong
LIQUIDITY_FLOOR = MIN_VOLUME_RATIO_20D
LIQUIDITY_CEILING = Decimal("2.00")

# Fixed weights, sum to 1.00; probability and confidence are model-driven signals and
# together carry 60% of the score, technical trend/liquidity the remaining 40%.
WEIGHT_PROBABILITY = Decimal("0.40")
WEIGHT_CONFIDENCE = Decimal("0.20")
WEIGHT_TREND = Decimal("0.25")
WEIGHT_LIQUIDITY = Decimal("0.15")


class InsufficientScoringDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScoringInputs:
    predicted_probability: Decimal | None
    confidence: Decimal | None
    sma20_distance: Decimal | None
    volume_ratio_20d: Decimal | None


@dataclass(frozen=True)
class ComponentScore:
    name: str
    raw_value: Decimal
    normalized_value: Decimal
    weight: Decimal
    contribution: Decimal
    detail: str


@dataclass(frozen=True)
class ScoreResult:
    contract_version: str
    total_score: Decimal
    components: tuple[ComponentScore, ...]


def _clamp01(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), value))


def _normalize(value: Decimal, floor: Decimal, ceiling: Decimal) -> Decimal:
    if ceiling == floor:
        raise ValueError("ceiling and floor must differ")
    return _clamp01((value - floor) / (ceiling - floor))


def compute_positive_opportunity_score(inputs: ScoringInputs) -> ScoreResult:
    """Deterministically score a positive-consensus-qualifying candidate. Missing
    inputs raise `InsufficientScoringDataError` naming the field; out-of-domain values
    (a probability/confidence outside [0, 1], a negative volume ratio) raise
    `ValueError` -- neither is ever silently defaulted to a score."""
    missing = [
        field
        for field, value in (
            ("predicted_probability", inputs.predicted_probability),
            ("confidence", inputs.confidence),
            ("sma20_distance", inputs.sma20_distance),
            ("volume_ratio_20d", inputs.volume_ratio_20d),
        )
        if value is None
    ]
    if missing:
        raise InsufficientScoringDataError(f"cannot score candidate: missing {missing}")

    if not (Decimal("0") <= inputs.predicted_probability <= Decimal("1")):
        raise ValueError(f"predicted_probability must be within [0, 1], got {inputs.predicted_probability}")
    if not (Decimal("0") <= inputs.confidence <= Decimal("1")):
        raise ValueError(f"confidence must be within [0, 1], got {inputs.confidence}")
    if inputs.volume_ratio_20d < 0:
        raise ValueError(f"volume_ratio_20d must be non-negative, got {inputs.volume_ratio_20d}")

    components = []

    norm = _normalize(inputs.predicted_probability, PROBABILITY_FLOOR, PROBABILITY_CEILING)
    components.append(ComponentScore(
        "probability", inputs.predicted_probability, norm, WEIGHT_PROBABILITY, norm * WEIGHT_PROBABILITY,
        f"predicted_probability={inputs.predicted_probability} normalized over [{PROBABILITY_FLOOR}, {PROBABILITY_CEILING}] -> {norm}",
    ))

    norm = _normalize(inputs.confidence, CONFIDENCE_FLOOR, CONFIDENCE_CEILING)
    components.append(ComponentScore(
        "confidence", inputs.confidence, norm, WEIGHT_CONFIDENCE, norm * WEIGHT_CONFIDENCE,
        f"confidence={inputs.confidence} normalized over [{CONFIDENCE_FLOOR}, {CONFIDENCE_CEILING}] -> {norm}",
    ))

    # trend has no meaningful floor (the consensus gate already requires > 0); a
    # non-positive value here simply saturates to a 0 contribution, not an error.
    norm = _clamp01(inputs.sma20_distance / TREND_CEILING)
    components.append(ComponentScore(
        "trend", inputs.sma20_distance, norm, WEIGHT_TREND, norm * WEIGHT_TREND,
        f"sma20_distance={inputs.sma20_distance} normalized over [0, {TREND_CEILING}] -> {norm}",
    ))

    norm = _normalize(inputs.volume_ratio_20d, LIQUIDITY_FLOOR, LIQUIDITY_CEILING)
    components.append(ComponentScore(
        "liquidity", inputs.volume_ratio_20d, norm, WEIGHT_LIQUIDITY, norm * WEIGHT_LIQUIDITY,
        f"volume_ratio_20d={inputs.volume_ratio_20d} normalized over [{LIQUIDITY_FLOOR}, {LIQUIDITY_CEILING}] -> {norm}",
    ))

    total = sum((c.contribution for c in components), Decimal("0")) * Decimal("100")
    return ScoreResult(contract_version=CONTRACT_VERSION, total_score=total, components=tuple(components))


def rank_positive_opportunities(
    candidates: list[tuple[str, ScoreResult]],
) -> list[tuple[str, ScoreResult]]:
    """Rank qualifying candidates by score, descending. Exact ties break on the
    candidate key ascending, so ordering is fully deterministic and repeatable."""
    return sorted(candidates, key=lambda pair: (-pair[1].total_score, pair[0]))


def record_ranked_recommendation(
    session: Session,
    consensus_evaluation: ConsensusEvaluation,
    score_result: ScoreResult,
    **recommendation_kwargs,
) -> Prediction:
    """The only entry point that persists a positive recommendation with both its
    consensus qualification and its opportunity score traced. Raises
    `ConsensusNotQualifiedError` before touching the session if the candidate does not
    qualify -- scoring a non-qualifying candidate is meaningless, so this never
    silently ranks one."""
    if not consensus_evaluation.qualifies:
        failed = ", ".join(c.name for c in consensus_evaluation.failed_criteria())
        raise ConsensusNotQualifiedError(
            f"candidate does not qualify under {consensus_evaluation.contract_version}: failed {failed}"
        )
    return record_recommendation(
        session,
        consensus_contract_version=consensus_evaluation.contract_version,
        scoring_contract_version=score_result.contract_version,
        opportunity_score=score_result.total_score,
        **recommendation_kwargs,
    )
