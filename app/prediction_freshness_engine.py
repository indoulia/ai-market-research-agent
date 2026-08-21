"""EPIC-M1.105: continuously determine whether an active prediction
remains valid, and flag when material new information warrants a
revision -- composing M1.62's own revalidation outcome with the newer
signals this platform built after M1.62 shipped: M1.101's feature/
coverage drift and M1.103's provider consensus disagreement.

Never recomputes M1.62's own `UNCHANGED`/`UPDATED`/`WITHDRAWN`/`EXPIRED`
outcome -- `revalidate_recommendation` is reused unchanged and is itself
idempotent, so calling it here is not a duplicate computation. Any
outcome other than `UNCHANGED` already means M1.62 detected a material
change through its own checks (horizon expiry, stop/target proximity,
stale market data, model version change); this module's own
contribution is checking the newer evidence M1.62 has no way to know
about: is this prediction's model version currently drifting (M1.101),
or does independent-provider fundamental data for this stock currently
show material disagreement (M1.103)?

"Recalculate target, SL, probability, score and Trust Score when
justified" (scope) is deliberately NOT performed here -- that recompute-
and-version step is M1.55's `create_recommendation_revision` (which
this module never calls), matching the propose/gate split this platform
already established for every trust/eligibility signal since M1.80.
`revision_trigger_reason` reuses M1.55's own `REASON_MATERIAL_EVIDENCE_
CHANGE` vocabulary value rather than inventing a parallel one, so a
future orchestration step that wires this signal into
`create_recommendation_revision` needs no vocabulary translation.

"Invalidate stale predictions without presenting negative/cautious
states to users" (scope) holds structurally: no write path to
`Prediction`, `RecommendationSelection`, or any recommendation-facing
table exists here at all.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .feature_drift_monitor import MONITORED_FEATURES, get_coverage_drift_history, get_feature_drift_history
from .models import FundamentalConsensusAssessment, Prediction, PredictionFreshnessDecision
from .provider_evidence_consensus import VERDICT_MATERIAL_DISAGREEMENT
from .recommendation_revalidation import OUTCOME_UNCHANGED, revalidate_recommendation
from .recommendation_revision import REASON_MATERIAL_EVIDENCE_CHANGE

FRESHNESS_ENGINE_VERSION = "PFE-001"

TRIGGER_REVALIDATION_MATERIAL_CHANGE = "REVALIDATION_MATERIAL_CHANGE"
TRIGGER_FEATURE_DRIFT_DETECTED = "FEATURE_DRIFT_DETECTED"
TRIGGER_COVERAGE_DRIFT_DETECTED = "COVERAGE_DRIFT_DETECTED"
TRIGGER_FUNDAMENTAL_PROVIDER_DISAGREEMENT = "FUNDAMENTAL_PROVIDER_DISAGREEMENT"


def _drifting_features(session: Session, model_version: str) -> list[str]:
    drifting = []
    for feature_name in MONITORED_FEATURES:
        history = get_feature_drift_history(session, model_version=model_version, feature_name=feature_name)
        if history and history[-1].trust_reduction_recommended:
            drifting.append(feature_name)
    return drifting


def _latest_fundamental_disagreement(session: Session, stock_id: int) -> FundamentalConsensusAssessment | None:
    latest = session.scalar(
        select(FundamentalConsensusAssessment)
        .where(FundamentalConsensusAssessment.stock_id == stock_id)
        .order_by(FundamentalConsensusAssessment.evaluated_at.desc(), FundamentalConsensusAssessment.id.desc())
    )
    if latest is not None and latest.verdict == VERDICT_MATERIAL_DISAGREEMENT:
        return latest
    return None


def evaluate_prediction_freshness(
    session: Session, prediction: Prediction, *, evaluated_at: datetime
) -> PredictionFreshnessDecision:
    """Idempotent by `(prediction_id, evaluated_at)`."""
    existing = session.scalar(
        select(PredictionFreshnessDecision).where(
            PredictionFreshnessDecision.prediction_id == prediction.id,
            PredictionFreshnessDecision.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    revalidation = revalidate_recommendation(session, prediction, checked_at=evaluated_at)

    triggers: list[dict] = []
    if revalidation.outcome != OUTCOME_UNCHANGED:
        triggers.append({"trigger": TRIGGER_REVALIDATION_MATERIAL_CHANGE, "detail": revalidation.outcome})

    drifting_features = _drifting_features(session, prediction.model_version)
    if drifting_features:
        triggers.append({"trigger": TRIGGER_FEATURE_DRIFT_DETECTED, "detail": drifting_features})

    coverage_history = get_coverage_drift_history(session, prediction.model_version)
    if coverage_history and coverage_history[-1].trust_reduction_recommended:
        triggers.append({"trigger": TRIGGER_COVERAGE_DRIFT_DETECTED, "detail": None})

    fundamental_disagreement = _latest_fundamental_disagreement(session, prediction.stock_id)
    if fundamental_disagreement is not None:
        triggers.append({
            "trigger": TRIGGER_FUNDAMENTAL_PROVIDER_DISAGREEMENT,
            "detail": {"period_end_date": str(fundamental_disagreement.period_end_date)},
        })

    re_analysis_recommended = bool(triggers)
    revision_trigger_reason = REASON_MATERIAL_EVIDENCE_CHANGE if re_analysis_recommended else None

    decision = PredictionFreshnessDecision(
        prediction_id=prediction.id, revalidation_outcome=revalidation.outcome, triggers=triggers,
        re_analysis_recommended=re_analysis_recommended, revision_trigger_reason=revision_trigger_reason,
        evaluated_at=evaluated_at, engine_rule_version=FRESHNESS_ENGINE_VERSION,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def get_freshness_history(session: Session, prediction_id: int) -> tuple[PredictionFreshnessDecision, ...]:
    return tuple(
        session.scalars(
            select(PredictionFreshnessDecision)
            .where(PredictionFreshnessDecision.prediction_id == prediction_id)
            .order_by(PredictionFreshnessDecision.id.asc())
        ).all()
    )
