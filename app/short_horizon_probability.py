"""EPIC-M1.75: extend short-term recommendation outputs from a single
score/confidence value into calibrated, horizon-specific outcome
probabilities and risk distributions.

`SUPPORTED_HORIZON_DAYS = (1, 2, 3, 5, 7)` is the EPIC's own named
interface contract, deliberately including day 2 even though `app.
recommendations.VALID_HORIZON_DAYS = (1, 3, 5, 7)` never actually
produces a `Prediction` with `horizon_days == 2` today -- the same
honest, forward-compatible posture M1.46 already established for its
never-yet-populated MEDIUM/LONG horizon bands. Querying day 2 always
returns `VERDICT_INSUFFICIENT_SAMPLE` (zero real evidence), never a
fabricated number.

"Respect M1.74 evidence-quality state" (scope) means the calibration
sample itself is filtered to only the historical predictions whose own
M1.74 `EvidenceQualityDecision` was `STATE_SUFFICIENT` -- a prediction
never gated, or gated `INSUFFICIENT`/`LEAKAGE_DETECTED`, does not get to
quietly influence a probability someone else will rely on.

"Preserve score, confidence and confidence quality as separate concepts"
/ "existing recommendation contracts remain authoritative" (AC): this
module never reads or writes `Prediction.opportunity_score`/`confidence`,
and `HorizonProbabilityProfile` is an entirely new, additive table --
attaching a profile to a prediction (`get_probability_profile_for_
prediction`) is a pure read, never a mutation.

A profile is a property of one `(model_version, horizon_days)` cohort,
not of a single prediction -- the same "one check row per cohort,
segmented, append-only" shape M1.67's `ModelRegressionCheck` already
established, reused here for a different question (a calibrated
distribution, not a regression verdict).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .evidence_quality_gate import STATE_SUFFICIENT, get_quality_decision_history
from .models import HorizonProbabilityProfile, Prediction, PredictionOutcome
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

PROBABILITY_PROFILE_VERSION = "SHP-001"

# The EPIC's own named interface contract -- see module docstring for why
# day 2 is included despite never being produced by M1.10 today.
SUPPORTED_HORIZON_DAYS = (1, 2, 3, 5, 7)

VERDICT_CALIBRATED = "CALIBRATED"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

# The tenth-percentile realized return -- "downside distribution where
# evidence supports it" (scope), a fixed, documented, versioned choice.
DOWNSIDE_PERCENTILE = Decimal("0.10")


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _percentile(values: list[Decimal], pct: Decimal) -> Decimal:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct * Decimal(len(ordered) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = rank - Decimal(lower_index)
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _has_sufficient_evidence_quality(session: Session, prediction_id: int) -> bool:
    history = get_quality_decision_history(session, prediction_id)
    if not history:
        return False
    return history[-1].state == STATE_SUFFICIENT


def _evidence_quality_filtered_rows(
    session: Session, *, model_version: str, horizon_days: int
) -> list[tuple[Prediction, PredictionOutcome]]:
    rows = session.execute(
        select(Prediction, PredictionOutcome)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .where(
            Prediction.model_version == model_version,
            Prediction.horizon_days == horizon_days,
            PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")),
        )
    ).all()
    return [(p, o) for p, o in rows if _has_sufficient_evidence_quality(session, p.id)]


def compute_horizon_probability_profile(
    session: Session, *, model_version: str, horizon_days: int, computed_at: datetime
) -> HorizonProbabilityProfile:
    """Deterministic and reproducible given the same underlying, already-
    immutable evidence (AC: "outputs are reproducible and auditable").
    Never fabricates a probability from too little qualifying evidence
    (AC: "insufficient evidence/sample states are explicit"; non-goal:
    "presenting unsupported probabilities when samples are
    insufficient")."""
    rows = _evidence_quality_filtered_rows(session, model_version=model_version, horizon_days=horizon_days)
    sample_count = len(rows)

    if sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        verdict = VERDICT_INSUFFICIENT_SAMPLE
        positive_return_probability = None
        target_hit_probability = None
        stop_hit_probability = None
        expected_return = None
        downside_p10_return = None
    else:
        verdict = VERDICT_CALIBRATED
        returns = [outcome.actual_return for _, outcome in rows]
        positive_return_probability = _rate(sum(1 for r in returns if r > 0), sample_count)
        target_hit_probability = _rate(sum(1 for _, o in rows if o.target_hit), sample_count)
        stop_hit_probability = _rate(sum(1 for _, o in rows if o.stop_hit), sample_count)
        expected_return = sum(returns) / Decimal(sample_count)
        downside_p10_return = _percentile(returns, DOWNSIDE_PERCENTILE)

    profile = HorizonProbabilityProfile(
        model_version=model_version,
        horizon_days=horizon_days,
        sample_count=sample_count,
        positive_return_probability=positive_return_probability,
        target_hit_probability=target_hit_probability,
        stop_hit_probability=stop_hit_probability,
        expected_return=expected_return,
        downside_p10_return=downside_p10_return,
        verdict=verdict,
        computed_at=computed_at,
        profile_rule_version=PROBABILITY_PROFILE_VERSION,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def get_latest_probability_profile(
    session: Session, *, model_version: str, horizon_days: int
) -> HorizonProbabilityProfile | None:
    return session.scalar(
        select(HorizonProbabilityProfile)
        .where(HorizonProbabilityProfile.model_version == model_version, HorizonProbabilityProfile.horizon_days == horizon_days)
        .order_by(HorizonProbabilityProfile.id.desc())
    )


def get_probability_profile_for_prediction(session: Session, prediction: Prediction) -> HorizonProbabilityProfile | None:
    """Attaches the latest calibrated profile for this prediction's own
    `(model_version, horizon_days)` cohort -- a pure read, never a
    mutation of `prediction` itself (AC: "existing recommendation
    contracts remain authoritative")."""
    return get_latest_probability_profile(session, model_version=prediction.model_version, horizon_days=prediction.horizon_days)


def get_profile_history(session: Session, *, model_version: str, horizon_days: int) -> tuple[HorizonProbabilityProfile, ...]:
    return tuple(
        session.scalars(
            select(HorizonProbabilityProfile)
            .where(HorizonProbabilityProfile.model_version == model_version, HorizonProbabilityProfile.horizon_days == horizon_days)
            .order_by(HorizonProbabilityProfile.id.asc())
        ).all()
    )
