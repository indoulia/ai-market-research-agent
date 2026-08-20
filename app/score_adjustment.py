"""EPIC-M1.40: adjust recommendation scoring only when historical evidence
demonstrates a stable relationship between M1.9's score components and
realized outcomes -- never automatically, never on in-sample evidence alone.

Deliberately does not modify `app/scoring.py` (M1.9): that module's fixed
weights are the production formula every already-merged EPIC's `Prediction.
opportunity_score` was computed with. This module only measures each
component's historical correlation with success/failure, proposes a
candidate reweighting from that evidence, and tests the candidate strictly
out-of-sample against the untouched original -- mirroring M1.29's
calibration-candidate pattern (`EvaluationWindow`, disjoint training/
evaluation windows, an IMPROVED/NOT_IMPROVED out-of-sample verdict) applied
to score components instead of raw probability.

Reuses M1.9's own normalization logic and constants (`WEIGHT_*`, `*_FLOOR`/
`*_CEILING`) so a component's "contribution" here means exactly what it means
in production scoring -- this module never invents a second definition of
what a component's normalized value is.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate
from .out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from .outcome_measurement import OUTCOME_FAILURE, OUTCOME_SUCCESS, get_outcome_measurement
from .scoring import (
    CONFIDENCE_CEILING,
    CONFIDENCE_FLOOR,
    LIQUIDITY_CEILING,
    LIQUIDITY_FLOOR,
    PROBABILITY_CEILING,
    PROBABILITY_FLOOR,
    TREND_CEILING,
    WEIGHT_CONFIDENCE,
    WEIGHT_LIQUIDITY,
    WEIGHT_PROBABILITY,
    WEIGHT_TREND,
)
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

SCORE_ADJUSTMENT_VERSION = "ESA-001"

COMPONENT_PROBABILITY = "probability"
COMPONENT_CONFIDENCE = "confidence"
COMPONENT_TREND = "trend"
COMPONENT_LIQUIDITY = "liquidity"

_ORIGINAL_WEIGHTS = {
    COMPONENT_PROBABILITY: WEIGHT_PROBABILITY,
    COMPONENT_CONFIDENCE: WEIGHT_CONFIDENCE,
    COMPONENT_TREND: WEIGHT_TREND,
    COMPONENT_LIQUIDITY: WEIGHT_LIQUIDITY,
}

VERDICT_STABLE_SIGNAL = "STABLE_SIGNAL"
VERDICT_WEAK_SIGNAL = "WEAK_SIGNAL"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

VERDICT_IMPROVED = "IMPROVED"
VERDICT_NOT_IMPROVED = "NOT_IMPROVED"
VERDICT_NO_ADJUSTMENT_ELIGIBLE = "NO_ADJUSTMENT_ELIGIBLE"

# A success/failure contribution gap at or beyond this margin, with
# sufficient sample, is a measurable ("stable") signal rather than noise.
# Fixed, documented, versioned policy constant.
STABLE_SIGNAL_GAP_THRESHOLD = Decimal("0.05")

# Same out-of-sample improvement bar M1.29 uses for its calibration
# candidate, reused here for consistency across this platform's evidence-
# gated adjustment EPICs.
IMPROVEMENT_MARGIN = Decimal("0.02")


class InsufficientEvidenceError(RuntimeError):
    """Raised when attempting to apply a candidate that was never made
    eligible (no `candidate_weights`) -- there is nothing to apply."""


@dataclass(frozen=True)
class ComponentCorrelation:
    component: str
    sample_count: int
    average_contribution_when_success: Decimal | None
    average_contribution_when_failure: Decimal | None
    contribution_gap: Decimal | None
    verdict: str


@dataclass(frozen=True)
class ScoreAdjustmentCandidate:
    version: str
    training_window: EvaluationWindow
    component_correlations: tuple[ComponentCorrelation, ...]
    candidate_weights: dict | None


@dataclass(frozen=True)
class ScoreAdjustmentComparisonResult:
    version: str
    evaluation_window: EvaluationWindow
    evaluated_count: int
    baseline_mean_absolute_error: Decimal | None
    candidate_mean_absolute_error: Decimal | None
    verdict: str


def _clamp01(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), value))


def _normalize(value: Decimal, floor: Decimal, ceiling: Decimal) -> Decimal:
    if ceiling == floor:
        return Decimal("0")
    return _clamp01((value - floor) / (ceiling - floor))


def _component_contributions(candidate: ScanCandidate) -> dict:
    """Recompute each component's *normalized* value (before weighting) from
    the same raw `ScanCandidate` inputs M1.9 itself scores from -- identical
    normalization logic and constants, reimplemented here rather than
    calling M1.9's private helpers across a module boundary."""
    return {
        COMPONENT_PROBABILITY: _normalize(candidate.predicted_probability, PROBABILITY_FLOOR, PROBABILITY_CEILING),
        COMPONENT_CONFIDENCE: _normalize(candidate.confidence, CONFIDENCE_FLOOR, CONFIDENCE_CEILING),
        COMPONENT_TREND: _clamp01(candidate.sma20_distance / TREND_CEILING),
        COMPONENT_LIQUIDITY: _normalize(candidate.volume_ratio_20d, LIQUIDITY_FLOOR, LIQUIDITY_CEILING),
    }


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _evaluated_with_candidates_in_window(
    session: Session, window: EvaluationWindow
) -> list[tuple[Prediction, str, ScanCandidate]]:
    """Every evaluated (M1.38 `SUCCESS`/`FAILURE`, `NEUTRAL` and
    `INSUFFICIENT_DATA` excluded as non-directional) prediction in `window`
    that still has a traceable `ScanCandidate` -- the raw inputs this module
    needs to recompute component contributions from."""
    query = select(Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate).join(
        PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id
    ).join(
        RecommendationGeneration, RecommendationGeneration.prediction_id == Prediction.id
    ).join(
        ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id
    )
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)

    results = []
    for prediction, outcome, _generation, scan_candidate in session.execute(query).all():
        measurement = get_outcome_measurement(session, outcome.id)
        if measurement is None or measurement.outcome_classification not in (OUTCOME_SUCCESS, OUTCOME_FAILURE):
            continue
        results.append((prediction, measurement.outcome_classification, scan_candidate))
    return results


def analyze_component_correlations(
    session: Session, window: EvaluationWindow
) -> tuple[ComponentCorrelation, ...]:
    """Measure each score component's historical correlation with success
    vs. failure over `window` (scope items 1-2)."""
    rows = _evaluated_with_candidates_in_window(session, window)

    correlations = []
    for component in (COMPONENT_PROBABILITY, COMPONENT_CONFIDENCE, COMPONENT_TREND, COMPONENT_LIQUIDITY):
        success_values = []
        failure_values = []
        for _prediction, classification, scan_candidate in rows:
            value = _component_contributions(scan_candidate)[component]
            (success_values if classification == OUTCOME_SUCCESS else failure_values).append(value)

        sample_count = len(success_values) + len(failure_values)
        avg_success = _mean(success_values)
        avg_failure = _mean(failure_values)
        gap = avg_success - avg_failure if avg_success is not None and avg_failure is not None else None

        if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or gap is None:
            verdict = VERDICT_INSUFFICIENT_SAMPLE
        elif gap >= STABLE_SIGNAL_GAP_THRESHOLD:
            verdict = VERDICT_STABLE_SIGNAL
        else:
            verdict = VERDICT_WEAK_SIGNAL

        correlations.append(
            ComponentCorrelation(
                component=component,
                sample_count=sample_count,
                average_contribution_when_success=avg_success,
                average_contribution_when_failure=avg_failure,
                contribution_gap=gap,
                verdict=verdict,
            )
        )
    return tuple(correlations)


def build_score_adjustment_candidate(
    session: Session, training_window: EvaluationWindow
) -> ScoreAdjustmentCandidate:
    """Propose a candidate reweighting only when *every* component has
    cleared the minimum-sample floor (scope: "require minimum evidence
    thresholds before an adjustment is eligible" -- partial evidence never
    triggers a partial reweighting). A component with a larger measured
    success/failure gap is proportionally up-weighted, one with a smaller or
    negative gap is proportionally down-weighted, then all four are
    renormalized to sum to `1.00` again -- a fixed, documented, versioned
    formula, not a fitted or optimized one."""
    correlations = analyze_component_correlations(session, training_window)

    if any(c.verdict == VERDICT_INSUFFICIENT_SAMPLE for c in correlations):
        return ScoreAdjustmentCandidate(
            version=SCORE_ADJUSTMENT_VERSION,
            training_window=training_window,
            component_correlations=correlations,
            candidate_weights=None,
        )

    raw_weights = {
        c.component: _ORIGINAL_WEIGHTS[c.component] * (Decimal("1") + max(Decimal("0"), c.contribution_gap))
        for c in correlations
    }
    total = sum(raw_weights.values(), Decimal("0"))
    candidate_weights = {component: weight / total for component, weight in raw_weights.items()}

    return ScoreAdjustmentCandidate(
        version=SCORE_ADJUSTMENT_VERSION,
        training_window=training_window,
        component_correlations=correlations,
        candidate_weights=candidate_weights,
    )


def apply_score_adjustment_candidate(candidate: ScoreAdjustmentCandidate, scan_candidate: ScanCandidate) -> Decimal:
    """Compute the *adjusted* score for one candidate's raw inputs, using
    `candidate.candidate_weights` instead of M1.9's fixed weights. Returns a
    new value; `Prediction.opportunity_score` (the original) is never
    touched anywhere in this module (scope: "preserve the original score
    alongside adjusted score")."""
    if candidate.candidate_weights is None:
        raise InsufficientEvidenceError(
            "this candidate has no eligible weights (insufficient training-window evidence)"
        )
    contributions = _component_contributions(scan_candidate)
    total = sum(
        (contributions[component] * weight for component, weight in candidate.candidate_weights.items()),
        Decimal("0"),
    )
    return total * Decimal("100")


def evaluate_score_adjustment_out_of_sample(
    session: Session, candidate: ScoreAdjustmentCandidate, evaluation_window: EvaluationWindow
) -> ScoreAdjustmentComparisonResult:
    """Test the candidate strictly out-of-sample against the untouched
    original score (AC: "adjustments are evaluated on unseen data"). Returns
    `NO_ADJUSTMENT_ELIGIBLE` immediately, without even querying the
    evaluation window, if the candidate was never made eligible (AC: "no
    adjustment occurs without sufficient historical evidence")."""
    if candidate.candidate_weights is None:
        return ScoreAdjustmentComparisonResult(
            version=SCORE_ADJUSTMENT_VERSION,
            evaluation_window=evaluation_window,
            evaluated_count=0,
            baseline_mean_absolute_error=None,
            candidate_mean_absolute_error=None,
            verdict=VERDICT_NO_ADJUSTMENT_ELIGIBLE,
        )

    if _windows_overlap(candidate.training_window, evaluation_window):
        raise OverlappingEvaluationWindowsError(
            f"evaluation window '{evaluation_window.label}' overlaps the candidate's "
            f"training window '{candidate.training_window.label}'"
        )

    rows = _evaluated_with_candidates_in_window(session, evaluation_window)
    if len(rows) < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        return ScoreAdjustmentComparisonResult(
            version=SCORE_ADJUSTMENT_VERSION,
            evaluation_window=evaluation_window,
            evaluated_count=len(rows),
            baseline_mean_absolute_error=None,
            candidate_mean_absolute_error=None,
            verdict=VERDICT_INSUFFICIENT_SAMPLE,
        )

    baseline_errors = []
    candidate_errors = []
    for prediction, classification, scan_candidate in rows:
        actual = Decimal("1") if classification == OUTCOME_SUCCESS else Decimal("0")
        baseline_errors.append(abs(prediction.opportunity_score / Decimal("100") - actual))
        adjusted = apply_score_adjustment_candidate(candidate, scan_candidate)
        candidate_errors.append(abs(adjusted / Decimal("100") - actual))

    baseline_mae = _mean(baseline_errors)
    candidate_mae = _mean(candidate_errors)
    verdict = VERDICT_IMPROVED if candidate_mae <= baseline_mae - IMPROVEMENT_MARGIN else VERDICT_NOT_IMPROVED

    return ScoreAdjustmentComparisonResult(
        version=SCORE_ADJUSTMENT_VERSION,
        evaluation_window=evaluation_window,
        evaluated_count=len(rows),
        baseline_mean_absolute_error=baseline_mae,
        candidate_mean_absolute_error=candidate_mae,
        verdict=verdict,
    )


def _windows_overlap(a: EvaluationWindow, b: EvaluationWindow) -> bool:
    if a.end is not None and b.start is not None and a.end < b.start:
        return False
    if b.end is not None and a.start is not None and b.end < a.start:
        return False
    return True
