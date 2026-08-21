"""EPIC-M1.122: make MRA's probability/confidence/Trust Score statistically
defensible by attaching an evidence-strength and uncertainty picture to a
prediction, instead of treating a point probability/success-rate as if it
were exact.

Reuses rather than recomputes: the sample size and observed success rate
this module estimates a confidence interval over are M1.104's own
(`segment_calibration.assess_segment_calibration`) -- the same
hierarchical stock->setup->sector->market-cap->horizon->global fallback
that already refuses to report a number from a segment too sparse to
trust (M1.11's `MIN_SAMPLE_SIZE`). Market/model uncertainty are M1.102's
own (`regime_transition_intelligence`) `uncertainty_source` vocabulary,
read via its snapshot getter -- never recomputed here. Data uncertainty is
M1.74's own evidence-quality-gate state, read the same way
`prediction_trust_score` already reads it.

The one genuinely new statistical measure this module contributes is the
**confidence interval around the observed success rate itself** (a Wilson
score interval, chosen over the naive normal approximation because it
stays inside [0, 1] and remains sensible at the small/extreme-proportion
samples this platform's segments actually produce) -- this is what lets
"3 wins out of 3" be told apart from "300 wins out of 300": both have
`observed_rate == 1`, but only the second has a tight interval, so only
the second earns `EVIDENCE_STRENGTH_STRONG` (scope: "prevent small-sample
high-success histories from producing artificially high Trust").

Propose-only: no write path to `Prediction`, `PredictionTrustScore`,
`PositiveRecommendationGateDecision`, or `SegmentCalibrationAssessment`
itself -- "integrate uncertainty and evidence strength into Trust Score
and positive-only eligibility" (scope) remains a future revision's job to
compose, the same posture M1.101/M1.102/M1.104's own signals already
established before being composed into anything.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .calibration import INSUFFICIENT_SAMPLE, MIN_SAMPLE_SIZE
from .evidence_quality_gate import STATE_INSUFFICIENT, STATE_LEAKAGE_DETECTED, get_quality_decision_history
from .models import Prediction, PredictionReliabilityAssessment, RegimeTransitionAssessment
from .regime_transition_intelligence import get_regime_uncertainty_snapshot
from .segment_calibration import assess_segment_calibration

RELIABILITY_RULE_VERSION = "PRU-001"

# 95% two-sided Wilson score interval -- fixed, documented, not fitted.
Z_95 = Decimal("1.96")

EVIDENCE_STRENGTH_INSUFFICIENT = "INSUFFICIENT"
EVIDENCE_STRENGTH_LOW = "LOW"
EVIDENCE_STRENGTH_MODERATE = "MODERATE"
EVIDENCE_STRENGTH_STRONG = "STRONG"

# Fixed, documented, versioned confidence-interval half-width bands. A
# segment can clear M1.11's MIN_SAMPLE_SIZE floor and still be too
# uncertain to call STRONG -- the interval, not the raw count, is what
# actually measures evidence strength (scope's own distinction between
# "sample size" and "evidence-strength" as two separate required outputs).
STRONG_CI_HALF_WIDTH = Decimal("0.05")
MODERATE_CI_HALF_WIDTH = Decimal("0.15")

REASON_INSUFFICIENT_SAMPLE_SIZE = "INSUFFICIENT_SAMPLE_SIZE"
REASON_WIDE_CONFIDENCE_INTERVAL = "WIDE_CONFIDENCE_INTERVAL"
REASON_DATA_QUALITY_INSUFFICIENT = "DATA_QUALITY_INSUFFICIENT"
REASON_MARKET_REGIME_UNCERTAIN = "MARKET_REGIME_UNCERTAIN"
REASON_MODEL_DRIFT_UNCERTAIN = "MODEL_DRIFT_UNCERTAIN"


def _wilson_score_interval(observed_rate: Decimal, sample_count: int) -> tuple[Decimal, Decimal]:
    p = float(observed_rate)
    n = float(sample_count)
    z = float(Z_95)
    denominator = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5
    lower = max(0.0, (center - margin) / denominator)
    upper = min(1.0, (center + margin) / denominator)
    return Decimal(str(lower)), Decimal(str(upper))


def _evidence_strength(ci_half_width: Decimal) -> str:
    if ci_half_width <= STRONG_CI_HALF_WIDTH:
        return EVIDENCE_STRENGTH_STRONG
    if ci_half_width <= MODERATE_CI_HALF_WIDTH:
        return EVIDENCE_STRENGTH_MODERATE
    return EVIDENCE_STRENGTH_LOW


def _data_uncertain(session: Session, prediction_id: int) -> bool:
    history = get_quality_decision_history(session, prediction_id)
    if not history:
        return False
    return history[-1].state in (STATE_INSUFFICIENT, STATE_LEAKAGE_DETECTED)


def _uncertainty_source(session: Session, prediction_id: int) -> str | None:
    """`None` means "not checked this run" (M1.102 has no regime-transition
    snapshot yet for this prediction), never "no uncertainty found" --
    the same honest-absence posture M1.115's provider-drift check uses."""
    snapshot = get_regime_uncertainty_snapshot(session, prediction_id)
    if snapshot is None:
        return None
    assessment = session.get(RegimeTransitionAssessment, snapshot.regime_transition_assessment_id)
    return assessment.uncertainty_source if assessment is not None else None


def assess_prediction_reliability(
    session: Session, prediction: Prediction, *, assessed_at: datetime, model_version: str | None = None
) -> PredictionReliabilityAssessment:
    """Idempotent by `(prediction_id, assessed_at)`."""
    existing = session.scalar(
        select(PredictionReliabilityAssessment).where(
            PredictionReliabilityAssessment.prediction_id == prediction.id,
            PredictionReliabilityAssessment.assessed_at == assessed_at,
        )
    )
    if existing is not None:
        return existing

    calibration = assess_segment_calibration(session, prediction, model_version=model_version, evaluated_at=assessed_at)

    reasons: list[str] = []
    data_uncertain = _data_uncertain(session, prediction.id)
    uncertainty_source = _uncertainty_source(session, prediction.id)

    if calibration.verdict == INSUFFICIENT_SAMPLE or calibration.resolved_sample_count < MIN_SAMPLE_SIZE or calibration.observed_rate is None:
        evidence_strength = EVIDENCE_STRENGTH_INSUFFICIENT
        confidence_interval_lower = None
        confidence_interval_upper = None
        confidence_interval_half_width = None
        reasons.append(REASON_INSUFFICIENT_SAMPLE_SIZE)
    else:
        confidence_interval_lower, confidence_interval_upper = _wilson_score_interval(
            calibration.observed_rate, calibration.resolved_sample_count
        )
        confidence_interval_half_width = (confidence_interval_upper - confidence_interval_lower) / Decimal("2")
        evidence_strength = _evidence_strength(confidence_interval_half_width)
        if evidence_strength == EVIDENCE_STRENGTH_LOW:
            reasons.append(REASON_WIDE_CONFIDENCE_INTERVAL)

    if data_uncertain:
        reasons.append(REASON_DATA_QUALITY_INSUFFICIENT)
    if uncertainty_source in ("MARKET", "MARKET_AND_MODEL"):
        reasons.append(REASON_MARKET_REGIME_UNCERTAIN)
    if uncertainty_source in ("MODEL", "MARKET_AND_MODEL"):
        reasons.append(REASON_MODEL_DRIFT_UNCERTAIN)

    reliable = evidence_strength in (EVIDENCE_STRENGTH_MODERATE, EVIDENCE_STRENGTH_STRONG) and not data_uncertain

    assessment = PredictionReliabilityAssessment(
        prediction_id=prediction.id,
        resolved_segment_level=calibration.resolved_segment_level,
        resolved_sample_count=calibration.resolved_sample_count,
        observed_rate=calibration.observed_rate,
        confidence_interval_lower=confidence_interval_lower,
        confidence_interval_upper=confidence_interval_upper,
        confidence_interval_half_width=confidence_interval_half_width,
        evidence_strength=evidence_strength,
        uncertainty_source=uncertainty_source,
        data_uncertain=data_uncertain,
        reliable=reliable,
        reasons=reasons,
        assessed_at=assessed_at,
        reliability_rule_version=RELIABILITY_RULE_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_reliability_history(session: Session, prediction_id: int) -> tuple[PredictionReliabilityAssessment, ...]:
    return tuple(
        session.scalars(
            select(PredictionReliabilityAssessment)
            .where(PredictionReliabilityAssessment.prediction_id == prediction_id)
            .order_by(PredictionReliabilityAssessment.id.asc())
        ).all()
    )
