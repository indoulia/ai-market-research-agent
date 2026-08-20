"""EPIC-M1.41: make recommendation scoring sensitive to market regime only
where historical evidence shows the current regime-neutral score is
systematically miscalibrated within a specific regime -- never automatically,
never on in-sample evidence alone, and never by mutating the original score.

Reuses M1.26's `classify_market_regime` (idempotent, point-in-time, versioned
via `REGIME_RULE_VERSION`) to attach a regime to every prediction analyzed
here -- since a prediction only exists for an *eligible* `ScanCandidate`, and
`classify_market_regime` only fails when a scan has zero eligible candidates,
classification always succeeds for a prediction's own scan. This gives every
eligible recommendation a point-in-time regime classification (AC), not just
a "where available" one.

Reuses M1.29's calibration vocabulary (`VERDICT_OVERCONFIDENT`/
`VERDICT_UNDERCONFIDENT`/`VERDICT_WELL_CALIBRATED`/`VERDICT_INSUFFICIENT_SAMPLE`,
`CALIBRATION_ERROR_MARGIN`) and M1.16's `MIN_SAMPLE_SIZE_FOR_COMPARISON` --
the same "is this segment's evidence reliable and does it show a stable
bias" question, segmented by regime instead of probability bucket. Reuses
M1.25's `EvaluationWindow`/`OverlappingEvaluationWindowsError` for the
disjoint train/evaluate abstraction, and M1.40's out-of-sample MAE-comparison
pattern applied to `Prediction.opportunity_score` instead of score
components.

`app/scoring.py` (M1.9) is never modified; `Prediction.opportunity_score` and
`MarketRegime.regime` are never written to by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .confidence_analysis import (
    CALIBRATION_ERROR_MARGIN,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_OVERCONFIDENT,
    VERDICT_UNDERCONFIDENT,
    VERDICT_WELL_CALIBRATED,
)
from .market_regime import classify_market_regime
from .models import Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate
from .out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

REGIME_SCORE_ADJUSTMENT_VERSION = "RAS-001"

VERDICT_IMPROVED = "IMPROVED"
VERDICT_NOT_IMPROVED = "NOT_IMPROVED"
VERDICT_NO_ADJUSTMENT_ELIGIBLE = "NO_ADJUSTMENT_ELIGIBLE"

# A candidate's mean absolute error must fall below the regime-neutral
# baseline's error by at least this margin, on the out-of-sample window, to
# be called an improvement rather than noise. Fixed, documented, versioned.
IMPROVEMENT_MARGIN = Decimal("0.02")


@dataclass(frozen=True)
class RegimePerformance:
    regime: str
    sample_count: int
    average_normalized_score: Decimal | None
    observed_success_rate: Decimal | None
    calibration_error: Decimal | None
    verdict: str


@dataclass(frozen=True)
class RegimeScoreAdjustmentCandidate:
    version: str
    training_window: EvaluationWindow
    performance: tuple[RegimePerformance, ...]
    regime_offsets: dict


@dataclass(frozen=True)
class RegimeScoreComparisonResult:
    version: str
    evaluation_window: EvaluationWindow
    evaluated_count: int
    baseline_mean_absolute_error: Decimal | None
    candidate_mean_absolute_error: Decimal | None
    verdict: str


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _clamp01(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), value))


def _normalized_score(prediction: Prediction) -> Decimal:
    return _clamp01(prediction.opportunity_score / Decimal("100"))


def _regime_for_prediction(session: Session, prediction: Prediction) -> str:
    """Every prediction traces to the eligible `ScanCandidate` it was
    generated from, so classification always succeeds -- never a
    'where available' fallback for this EPIC (AC: "every eligible
    recommendation has a point-in-time regime classification")."""
    scan_id = session.execute(
        select(ScanCandidate.scan_id)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalar_one()
    regime = classify_market_regime(session, scan_id)
    return regime.regime


def _evaluated_in_window(session: Session, window: EvaluationWindow) -> list[tuple[Prediction, PredictionOutcome]]:
    query = select(Prediction, PredictionOutcome).join(
        PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id
    ).where(PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    return list(session.execute(query).all())


def _windows_overlap(a: EvaluationWindow, b: EvaluationWindow) -> bool:
    if a.end is not None and b.start is not None and a.end < b.start:
        return False
    if b.end is not None and a.start is not None and b.end < a.start:
        return False
    return True


def _calibration_verdict(sample_count: int, calibration_error: Decimal | None) -> str:
    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or calibration_error is None:
        return VERDICT_INSUFFICIENT_SAMPLE
    if calibration_error >= CALIBRATION_ERROR_MARGIN:
        return VERDICT_OVERCONFIDENT
    if calibration_error <= -CALIBRATION_ERROR_MARGIN:
        return VERDICT_UNDERCONFIDENT
    return VERDICT_WELL_CALIBRATED


def analyze_regime_performance(
    session: Session, window: EvaluationWindow
) -> tuple[RegimePerformance, ...]:
    """Measure regime-neutral score performance segmented by regime over
    `window` (scope: "measure score/outcome performance by regime")."""
    evaluated = _evaluated_in_window(session, window)

    by_regime: dict[str, list[tuple[Prediction, PredictionOutcome]]] = {}
    for prediction, outcome in evaluated:
        regime = _regime_for_prediction(session, prediction)
        by_regime.setdefault(regime, []).append((prediction, outcome))

    performance = []
    for regime in sorted(by_regime):
        rows = by_regime[regime]
        success_count = sum(1 for _, o in rows if o.outcome == "SUCCESS")
        observed_rate = Decimal(success_count) / Decimal(len(rows)) if rows else None
        average_score = _mean([_normalized_score(p) for p, _ in rows])
        calibration_error = (
            average_score - observed_rate if average_score is not None and observed_rate is not None else None
        )
        performance.append(
            RegimePerformance(
                regime=regime,
                sample_count=len(rows),
                average_normalized_score=average_score,
                observed_success_rate=observed_rate,
                calibration_error=calibration_error,
                verdict=_calibration_verdict(len(rows), calibration_error),
            )
        )
    return tuple(performance)


def build_regime_score_adjustment_candidate(
    session: Session, training_window: EvaluationWindow
) -> RegimeScoreAdjustmentCandidate:
    """Propose a per-regime score offset only for regimes whose training-
    window evidence clears `MIN_SAMPLE_SIZE_FOR_COMPARISON` *and* shows a
    calibration error large enough to call stable (`OVERCONFIDENT`/
    `UNDERCONFIDENT`) -- a well-calibrated or insufficiently-evidenced regime
    is left out of `regime_offsets` entirely and falls back to the
    regime-neutral baseline (scope: "avoid ... adjustment without evidence";
    AC: "no regime adjustment is enabled without evidence")."""
    performance = analyze_regime_performance(session, training_window)
    regime_offsets = {
        p.regime: p.calibration_error
        for p in performance
        if p.verdict in (VERDICT_OVERCONFIDENT, VERDICT_UNDERCONFIDENT)
    }
    return RegimeScoreAdjustmentCandidate(
        version=REGIME_SCORE_ADJUSTMENT_VERSION,
        training_window=training_window,
        performance=performance,
        regime_offsets=regime_offsets,
    )


def apply_regime_score_adjustment(
    candidate: RegimeScoreAdjustmentCandidate, prediction: Prediction, regime: str
) -> Decimal:
    """Compute the regime-aware score for one prediction's regime. Returns
    the unadjusted (regime-neutral baseline) score unchanged for any regime
    without an eligible offset -- `Prediction.opportunity_score` itself is
    never read for writing anywhere in this module (AC: "historical
    recommendations retain their original regime and score")."""
    offset = candidate.regime_offsets.get(regime)
    if offset is None:
        return prediction.opportunity_score
    adjusted_normalized = _clamp01(_normalized_score(prediction) - offset)
    return adjusted_normalized * Decimal("100")


def evaluate_regime_score_adjustment_out_of_sample(
    session: Session, candidate: RegimeScoreAdjustmentCandidate, evaluation_window: EvaluationWindow
) -> RegimeScoreComparisonResult:
    """Test the candidate strictly out-of-sample against the regime-neutral
    baseline (AC: "regime-aware scoring is compared against the baseline
    out-of-sample"). Returns `NO_ADJUSTMENT_ELIGIBLE` immediately, without
    even querying the evaluation window, if no regime ever cleared the
    evidence threshold."""
    if not candidate.regime_offsets:
        return RegimeScoreComparisonResult(
            version=REGIME_SCORE_ADJUSTMENT_VERSION,
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

    evaluated = _evaluated_in_window(session, evaluation_window)
    if len(evaluated) < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        return RegimeScoreComparisonResult(
            version=REGIME_SCORE_ADJUSTMENT_VERSION,
            evaluation_window=evaluation_window,
            evaluated_count=len(evaluated),
            baseline_mean_absolute_error=None,
            candidate_mean_absolute_error=None,
            verdict=VERDICT_INSUFFICIENT_SAMPLE,
        )

    baseline_errors = []
    candidate_errors = []
    for prediction, outcome in evaluated:
        actual = Decimal("1") if outcome.outcome == "SUCCESS" else Decimal("0")
        baseline_errors.append(abs(_normalized_score(prediction) - actual))
        regime = _regime_for_prediction(session, prediction)
        adjusted = apply_regime_score_adjustment(candidate, prediction, regime) / Decimal("100")
        candidate_errors.append(abs(adjusted - actual))

    baseline_mae = _mean(baseline_errors)
    candidate_mae = _mean(candidate_errors)
    verdict = VERDICT_IMPROVED if candidate_mae <= baseline_mae - IMPROVEMENT_MARGIN else VERDICT_NOT_IMPROVED

    return RegimeScoreComparisonResult(
        version=REGIME_SCORE_ADJUSTMENT_VERSION,
        evaluation_window=evaluation_window,
        evaluated_count=len(evaluated),
        baseline_mean_absolute_error=baseline_mae,
        candidate_mean_absolute_error=candidate_mae,
        verdict=verdict,
    )
