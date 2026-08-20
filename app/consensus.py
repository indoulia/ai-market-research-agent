"""EPIC-M1.8: the positive-consensus contract -- the single, explicit, versioned,
deterministic decision layer that turns existing model/data signals into a positive
recommendation candidate. No LLM reasoning and no threshold learning from historical
outcomes belong here (that is a later calibration EPIC); every threshold below is a
fixed product/policy constant, bumped via CONTRACT_VERSION whenever changed.

Criteria draw only on signals already produced elsewhere in the repository:
- `predicted_probability` / `confidence`: the calibrated model output already stored on
  `Prediction` (app/prediction/baseline.py, app/recommendations.py).
- `sma20_distance` / `volume_ratio_20d`: technical features already computed by
  app/features/technical.py.
- `data_quality_passed`: the deterministic OHLCV validation outcome already produced by
  app/market_data/quality.py (`ValidationReport.is_valid`).
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from .models import Prediction
from .recommendations import record_recommendation

CONTRACT_VERSION = "PCC-001"

MIN_PREDICTED_PROBABILITY = Decimal("0.60")
MIN_CONFIDENCE = Decimal("0.55")
MIN_VOLUME_RATIO_20D = Decimal("0.75")


class ConsensusNotQualifiedError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConsensusInputs:
    predicted_probability: Decimal | None
    confidence: Decimal | None
    sma20_distance: Decimal | None
    volume_ratio_20d: Decimal | None
    data_quality_passed: bool | None


@dataclass(frozen=True)
class CriterionResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ConsensusEvaluation:
    contract_version: str
    qualifies: bool
    criteria: tuple[CriterionResult, ...]

    def failed_criteria(self) -> tuple[CriterionResult, ...]:
        return tuple(c for c in self.criteria if not c.passed)


def evaluate_positive_consensus(inputs: ConsensusInputs) -> ConsensusEvaluation:
    """Deterministically PASS/FAIL every required criterion; missing data always FAILs
    its criterion explicitly rather than being silently skipped or defaulted."""
    criteria = []

    if inputs.predicted_probability is None:
        criteria.append(CriterionResult("model_probability", False, "predicted_probability is missing"))
    else:
        passed = inputs.predicted_probability >= MIN_PREDICTED_PROBABILITY
        criteria.append(CriterionResult(
            "model_probability", passed,
            f"predicted_probability={inputs.predicted_probability} {'>=' if passed else '<'} {MIN_PREDICTED_PROBABILITY}",
        ))

    if inputs.confidence is None:
        criteria.append(CriterionResult("model_confidence", False, "confidence is missing"))
    else:
        passed = inputs.confidence >= MIN_CONFIDENCE
        criteria.append(CriterionResult(
            "model_confidence", passed,
            f"confidence={inputs.confidence} {'>=' if passed else '<'} {MIN_CONFIDENCE}",
        ))

    if inputs.sma20_distance is None:
        criteria.append(CriterionResult("positive_trend", False, "sma20_distance is missing"))
    else:
        passed = inputs.sma20_distance > 0
        criteria.append(CriterionResult(
            "positive_trend", passed,
            f"sma20_distance={inputs.sma20_distance} {'>' if passed else '<='} 0",
        ))

    if inputs.volume_ratio_20d is None:
        criteria.append(CriterionResult("sufficient_liquidity", False, "volume_ratio_20d is missing"))
    else:
        passed = inputs.volume_ratio_20d >= MIN_VOLUME_RATIO_20D
        criteria.append(CriterionResult(
            "sufficient_liquidity", passed,
            f"volume_ratio_20d={inputs.volume_ratio_20d} {'>=' if passed else '<'} {MIN_VOLUME_RATIO_20D}",
        ))

    if inputs.data_quality_passed is None:
        criteria.append(CriterionResult("data_quality", False, "data_quality_passed is missing"))
    else:
        criteria.append(CriterionResult(
            "data_quality", inputs.data_quality_passed,
            f"data_quality_passed={inputs.data_quality_passed}",
        ))

    return ConsensusEvaluation(
        contract_version=CONTRACT_VERSION,
        qualifies=all(c.passed for c in criteria),
        criteria=tuple(criteria),
    )


def record_qualifying_recommendation(session: Session, evaluation: ConsensusEvaluation, **recommendation_kwargs) -> Prediction:
    """The only entry point that persists a positive recommendation. Raises unless the
    positive-consensus contract qualifies the candidate -- enforces AC "a stock cannot
    become a positive recommendation unless the contract qualifies it" at the boundary,
    rather than leaving it to caller discipline."""
    if not evaluation.qualifies:
        failed = ", ".join(c.name for c in evaluation.failed_criteria())
        raise ConsensusNotQualifiedError(f"candidate does not qualify under {evaluation.contract_version}: failed {failed}")
    return record_recommendation(
        session,
        consensus_contract_version=evaluation.contract_version,
        **recommendation_kwargs,
    )
