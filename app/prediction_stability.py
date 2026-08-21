"""EPIC-M1.83: measure whether predictions remain stable under normal
information updates, and whether independent model versions agree on
the same opportunity.

**Stability** composes M1.55's own revision chain and its already-computed
`VersionComparison` deltas -- never recomputing them. M1.55's `create_
recommendation_revision` already *requires* a `revision_reason` from a
fixed vocabulary (`MATERIAL_EVIDENCE_CHANGE`/`EVIDENCE_STALE`/
`MANUAL_TRIGGER`), so no revision in this platform is ever literally
"unexplained" -- but `MANUAL_TRIGGER` is the one reason not backed by an
objective evidence/freshness signal. "Distinguish legitimate reaction to
new information from unexplained instability" (scope) is therefore
operationalized as: a high revision count or large deltas driven
substantially by `MANUAL_TRIGGER` revisions is `unexplained instability`;
the same frequency/magnitude driven by `MATERIAL_EVIDENCE_CHANGE`/
`EVIDENCE_STALE` is a legitimate reaction, still reported, but never
flagged for trust reduction on its own.

**Model agreement** is a genuinely, honestly forward-compatible
capability: this platform's production pipeline runs exactly one model
version at a time (each `ScanCandidate` carries a single `model_version`;
`RecommendationGeneration.scan_candidate_id` is unique, so there is no
real simultaneous-ensemble scoring today). Rather than fabricating
agreement data, `_find_agreement_candidate` looks for any other
`Prediction` on the *same stock*, from a *different* model version,
within a bounded time window -- if this platform ever runs two models
side by side (or a future EPIC adds one), this comparison becomes real
immediately; until then it honestly reports `NO_DISAGREEMENT_DATA`.

Execution Rule: "stability alone cannot increase trust; it becomes
positive evidence only when stable predictions demonstrate reliable
outcomes." `stability_backed_by_outcomes` requires BOTH `STABLE` and a
real, evaluated `SUCCESS` outcome on the active version -- never stability
alone.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Prediction, PredictionOutcome, PredictionStabilityAssessment
from .recommendation_revision import REASON_MANUAL_TRIGGER, compare_versions, get_active_version, get_revision_history

STABILITY_ASSESSMENT_VERSION = "PST-001"

STABILITY_VERDICT_STABLE = "STABLE"
STABILITY_VERDICT_UNSTABLE = "UNSTABLE"

AGREEMENT_VERDICT_AGREE = "AGREE"
AGREEMENT_VERDICT_DISAGREE = "DISAGREE"
AGREEMENT_VERDICT_NO_DATA = "NO_DISAGREEMENT_DATA"

# Fixed, documented, versioned policy constants -- not learned or fitted.
MAX_STABLE_REVISIONS = 2
MAX_STABLE_SCORE_DELTA = Decimal("15.00")
MODEL_AGREEMENT_SCORE_MARGIN = Decimal("15.00")
MODEL_AGREEMENT_TIME_WINDOW = timedelta(days=7)


def _find_agreement_candidate(session: Session, prediction: Prediction) -> Prediction | None:
    window_start = prediction.as_of_timestamp - MODEL_AGREEMENT_TIME_WINDOW
    window_end = prediction.as_of_timestamp + MODEL_AGREEMENT_TIME_WINDOW
    return session.scalar(
        select(Prediction)
        .where(
            Prediction.stock_id == prediction.stock_id,
            Prediction.model_version != prediction.model_version,
            Prediction.as_of_timestamp >= window_start,
            Prediction.as_of_timestamp <= window_end,
        )
        .order_by(Prediction.as_of_timestamp.asc())
    )


def _stability_backed_by_outcomes(session: Session, active_version: Prediction, stability_verdict: str) -> bool:
    if stability_verdict != STABILITY_VERDICT_STABLE:
        return False
    outcome = session.scalar(select(PredictionOutcome).where(PredictionOutcome.prediction_id == active_version.id))
    return outcome is not None and outcome.outcome == "SUCCESS"


def assess_prediction_stability(
    session: Session, original_prediction: Prediction, *, assessed_at: datetime
) -> PredictionStabilityAssessment:
    """Deterministic given M1.55's already-immutable revision chain
    (AC: "prediction stability is measurable per stock and horizon").
    Idempotent by `(original_prediction_id, assessed_at)`."""
    existing = session.scalar(
        select(PredictionStabilityAssessment).where(
            PredictionStabilityAssessment.original_prediction_id == original_prediction.id,
            PredictionStabilityAssessment.assessed_at == assessed_at,
        )
    )
    if existing is not None:
        return existing

    history = get_revision_history(session, original_prediction.id)
    revision_count = len(history)
    comparisons = [compare_versions(session, revision) for revision in history]

    max_score_delta = max((abs(c.opportunity_score_delta) for c in comparisons), default=None)
    max_confidence_delta = max((abs(c.confidence_delta) for c in comparisons), default=None)
    unexplained_revision_count = sum(1 for r in history if r.revision_reason == REASON_MANUAL_TRIGGER)

    is_unstable = revision_count > MAX_STABLE_REVISIONS or (
        max_score_delta is not None and max_score_delta > MAX_STABLE_SCORE_DELTA
    )
    stability_verdict = STABILITY_VERDICT_UNSTABLE if is_unstable else STABILITY_VERDICT_STABLE

    agreement_candidate = _find_agreement_candidate(session, original_prediction)
    if agreement_candidate is None:
        model_agreement_verdict = AGREEMENT_VERDICT_NO_DATA
        model_agreement_score_delta = None
    else:
        model_agreement_score_delta = abs(agreement_candidate.opportunity_score - original_prediction.opportunity_score)
        model_agreement_verdict = (
            AGREEMENT_VERDICT_AGREE if model_agreement_score_delta <= MODEL_AGREEMENT_SCORE_MARGIN else AGREEMENT_VERDICT_DISAGREE
        )

    active_version = get_active_version(session, original_prediction)
    stability_backed_by_outcomes = _stability_backed_by_outcomes(session, active_version, stability_verdict)

    trust_reduction_recommended = (
        (stability_verdict == STABILITY_VERDICT_UNSTABLE and unexplained_revision_count > 0)
        or model_agreement_verdict == AGREEMENT_VERDICT_DISAGREE
    )

    assessment = PredictionStabilityAssessment(
        original_prediction_id=original_prediction.id,
        revision_count=revision_count,
        max_score_delta=max_score_delta,
        max_confidence_delta=max_confidence_delta,
        unexplained_revision_count=unexplained_revision_count,
        stability_verdict=stability_verdict,
        model_agreement_verdict=model_agreement_verdict,
        model_agreement_score_delta=model_agreement_score_delta,
        stability_backed_by_outcomes=stability_backed_by_outcomes,
        trust_reduction_recommended=trust_reduction_recommended,
        assessed_at=assessed_at,
        assessment_rule_version=STABILITY_ASSESSMENT_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_stability_history(session: Session, original_prediction_id: int) -> tuple[PredictionStabilityAssessment, ...]:
    return tuple(
        session.scalars(
            select(PredictionStabilityAssessment)
            .where(PredictionStabilityAssessment.original_prediction_id == original_prediction_id)
            .order_by(PredictionStabilityAssessment.id.asc())
        ).all()
    )
