"""EPIC-M1.56: generate evidence-backed candidate adjustments to
recommendation scores, confidence, target/SL, or selection rules by
synthesizing three already-existing "candidate signal" sources into one
unified, versioned candidate shape -- never applying any of them to
production.

Composes rather than duplicates: M1.29's `adaptive_calibration` (predicted-
probability bucket miscalibration, out-of-sample validated), M1.41's
`regime_aware_scoring` (regime-specific score miscalibration, out-of-sample
validated), and M1.53's `feedback_learning_signals` (user-feedback patterns
correlated with poor outcomes -- these have no out-of-sample validation
mechanism of their own, so they are always surfaced `PENDING`, an honest
limitation rather than a fabricated validation). None of these three
source modules are modified.

"Preserve current production rules until promotion" (scope) holds
structurally: this module has no write path to `Prediction`,
`ScanCandidate`, or any scoring/selection table at all. It only proposes;
promoting a `VALIDATED` candidate into production is a decision for a
promotion-gate EPIC (the same "propose here, gate there" split M1.29/M1.30
already have with M1.31, and M1.43 has with M1.44).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from .adaptive_calibration import (
    VERDICT_IMPROVED as CAL_VERDICT_IMPROVED,
    VERDICT_NOT_IMPROVED as CAL_VERDICT_NOT_IMPROVED,
    build_calibration_candidate,
    evaluate_calibration_candidate_out_of_sample,
)
from .confidence_analysis import VERDICT_OVERCONFIDENT, VERDICT_UNDERCONFIDENT
from .discovery_effectiveness import VERDICT_WEAK as FEEDBACK_VERDICT_WEAK
from .feedback_learning_signals import compute_feedback_learning_signals
from .out_of_sample_validation import EvaluationWindow
from .regime_aware_scoring import (
    VERDICT_IMPROVED as REGIME_VERDICT_IMPROVED,
    VERDICT_NOT_IMPROVED as REGIME_VERDICT_NOT_IMPROVED,
    build_regime_score_adjustment_candidate,
    evaluate_regime_score_adjustment_out_of_sample,
)

ADAPTIVE_ADJUSTMENT_VERSION = "ARA-001"

SOURCE_PROBABILITY_CALIBRATION = "PROBABILITY_CALIBRATION"
SOURCE_REGIME_SCORE_ADJUSTMENT = "REGIME_SCORE_ADJUSTMENT"
SOURCE_FEEDBACK_LEARNING_SIGNAL = "FEEDBACK_LEARNING_SIGNAL"

STATUS_VALIDATED = "VALIDATED"
STATUS_REJECTED = "REJECTED"
STATUS_PENDING = "PENDING"


@dataclass(frozen=True)
class AdaptiveAdjustmentCandidate:
    version: str
    source_signal: str
    affected_condition: str
    rationale: str
    sample_size: int
    expected_impact: Decimal | None
    validation_status: str
    validation_detail: str


@dataclass(frozen=True)
class AdaptiveAdjustmentReport:
    version: str
    candidates: tuple[AdaptiveAdjustmentCandidate, ...]


def _mean(values: list) -> Decimal | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _calibration_candidates(
    session: Session, training_window: EvaluationWindow, evaluation_window: EvaluationWindow
) -> tuple[AdaptiveAdjustmentCandidate, ...]:
    """Identifies recurring under/over-confidence patterns in
    `predicted_probability` (scope: "identify recurring under/over-
    performance patterns") and validates the resulting candidate strictly
    out-of-sample (AC: "historical replay compares baseline and
    candidate")."""
    candidate = build_calibration_candidate(session, training_window)
    flagged = [b for b in candidate.buckets if b.verdict in (VERDICT_OVERCONFIDENT, VERDICT_UNDERCONFIDENT)]
    if not flagged:
        return ()

    comparison = evaluate_calibration_candidate_out_of_sample(session, candidate, evaluation_window)
    if comparison.verdict == CAL_VERDICT_IMPROVED:
        status = STATUS_VALIDATED
    elif comparison.verdict == CAL_VERDICT_NOT_IMPROVED:
        status = STATUS_REJECTED
    else:
        status = STATUS_PENDING

    affected = ", ".join(f"probability in [{b.lower}, {b.upper})" for b in flagged)
    rationale = "; ".join(
        f"bucket [{b.lower}, {b.upper}) is {b.verdict.lower()} by {b.calibration_error} over {b.sample_count} samples"
        for b in flagged
    )
    return (
        AdaptiveAdjustmentCandidate(
            version=ADAPTIVE_ADJUSTMENT_VERSION,
            source_signal=SOURCE_PROBABILITY_CALIBRATION,
            affected_condition=affected,
            rationale=rationale,
            sample_size=sum(b.sample_count for b in flagged),
            expected_impact=_mean([abs(b.calibration_error) for b in flagged]),
            validation_status=status,
            validation_detail=f"out-of-sample verdict={comparison.verdict}",
        ),
    )


def _regime_candidates(
    session: Session, training_window: EvaluationWindow, evaluation_window: EvaluationWindow
) -> tuple[AdaptiveAdjustmentCandidate, ...]:
    """Identifies recurring regime-specific score miscalibration and
    validates the resulting candidate strictly out-of-sample."""
    candidate = build_regime_score_adjustment_candidate(session, training_window)
    if not candidate.regime_offsets:
        return ()

    comparison = evaluate_regime_score_adjustment_out_of_sample(session, candidate, evaluation_window)
    if comparison.verdict == REGIME_VERDICT_IMPROVED:
        status = STATUS_VALIDATED
    elif comparison.verdict == REGIME_VERDICT_NOT_IMPROVED:
        status = STATUS_REJECTED
    else:
        status = STATUS_PENDING

    flagged = [p for p in candidate.performance if p.regime in candidate.regime_offsets]
    affected = ", ".join(sorted(candidate.regime_offsets))
    rationale = "; ".join(
        f"regime {p.regime} is {p.verdict.lower()} by {p.calibration_error} over {p.sample_count} samples"
        for p in flagged
    )
    return (
        AdaptiveAdjustmentCandidate(
            version=ADAPTIVE_ADJUSTMENT_VERSION,
            source_signal=SOURCE_REGIME_SCORE_ADJUSTMENT,
            affected_condition=affected,
            rationale=rationale,
            sample_size=sum(p.sample_count for p in flagged),
            expected_impact=_mean(list(candidate.regime_offsets.values())),
            validation_status=status,
            validation_detail=f"out-of-sample verdict={comparison.verdict}",
        ),
    )


def _feedback_candidates(session: Session) -> tuple[AdaptiveAdjustmentCandidate, ...]:
    """Identifies feedback categories/reasons that correlate with a lower
    success rate than baseline. These have no out-of-sample validation
    mechanism of their own -- always surfaced `PENDING`, an honest
    limitation rather than a fabricated validation (AC: "candidates with
    insufficient evidence are ... marked pending")."""
    report = compute_feedback_learning_signals(session)
    candidates = []
    for signal in report.signals:
        if signal.verdict != FEEDBACK_VERDICT_WEAK:
            continue
        candidates.append(
            AdaptiveAdjustmentCandidate(
                version=ADAPTIVE_ADJUSTMENT_VERSION,
                source_signal=SOURCE_FEEDBACK_LEARNING_SIGNAL,
                affected_condition=f"category={signal.category}, reason_code={signal.reason_code}",
                rationale=(
                    f"'{signal.reason_code}' feedback on '{signal.category}' precedes a success rate of "
                    f"{signal.success_rate} over {signal.evaluated_count} evaluated predictions, below baseline"
                ),
                sample_size=signal.evaluated_count,
                expected_impact=signal.success_rate,
                validation_status=STATUS_PENDING,
                validation_detail="feedback-derived patterns have no out-of-sample validation mechanism yet",
            )
        )
    return tuple(candidates)


def generate_adaptive_adjustment_candidates(
    session: Session, *, training_window: EvaluationWindow, evaluation_window: EvaluationWindow
) -> AdaptiveAdjustmentReport:
    """Deterministic and reproducible for the same inputs (AC): pure
    aggregation over M1.29/M1.41/M1.53's own already-deterministic outputs,
    no randomness anywhere. Never writes anything -- candidates are never
    applied directly to production (AC)."""
    candidates = (
        _calibration_candidates(session, training_window, evaluation_window)
        + _regime_candidates(session, training_window, evaluation_window)
        + _feedback_candidates(session)
    )
    return AdaptiveAdjustmentReport(version=ADAPTIVE_ADJUSTMENT_VERSION, candidates=candidates)
