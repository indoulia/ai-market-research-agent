"""EPIC-M1.115: detect when a historical prediction's own captured
policy versions or evidence-provider identities have since drifted from
the platform's current state, so a literal replay difference is
correctly attributed to environment drift rather than mistaken for a
real regression.

**Persist point-in-time input snapshots, provider identities, and
model/feature/configuration/policy versions**: already fully covered by
M1.66's `RecommendationDecisionTrace` -- every version field
(`model_version`/`feature_version`/`consensus_contract_version`/
`horizon_selection_version`/`scoring_contract_version`/`target_stop_
methodology_version`) and every evidence category's `source` (provider
identity) is already captured there, immutably, at decision time. Not
duplicated here.

**Reconstruct prediction revisions and decision traces / replay
historical predictions deterministically / compare replay output with
original output**: already M1.55's (`get_revision_history`), M1.66's
(`get_decision_trace`), and M1.24's (`replay_generation`) own jobs
respectively. Not duplicated here.

**Detect non-reproducible dependencies (this module's own, genuinely
new contribution)**: `audit_prediction_reproducibility` compares a
prediction's own trace against the platform's *current* live version
constants for each pipeline stage, and (when a live provider-id set is
supplied) each evidence category's captured `source` against what's
currently registered. Either kind of drift means literally re-running
today's code against today's providers cannot reproduce the original
decision *for reasons that have nothing to do with the model's
correctness* -- an environment-drift signal, not a regression signal
(M1.67's job). Read-only: no write path to `RecommendationDecisionTrace`
or any pipeline-version constant.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .consensus import CONTRACT_VERSION as CURRENT_CONSENSUS_VERSION
from .decision_trace import get_decision_trace
from .horizon import SELECTION_VERSION as CURRENT_HORIZON_SELECTION_VERSION
from .models import Prediction, RecommendationGeneration, ReproducibilityAuditDecision
from .recommendation_generator import GENERATOR_VERSION as CURRENT_GENERATOR_VERSION
from .scoring import CONTRACT_VERSION as CURRENT_SCORING_VERSION
from .target_stop_loss import TARGET_STOP_METHODOLOGY_VERSION as CURRENT_TARGET_STOP_VERSION

AUDIT_RULE_VERSION = "RPA-001"

# Fixed, documented mapping of trace field -> the current live constant it
# must match for a literal replay to be reproducible today.
_VERSION_FIELD_CHECKS = (
    ("consensus_contract_version", CURRENT_CONSENSUS_VERSION),
    ("scoring_contract_version", CURRENT_SCORING_VERSION),
    ("horizon_selection_version", CURRENT_HORIZON_SELECTION_VERSION),
    ("target_stop_methodology_version", CURRENT_TARGET_STOP_VERSION),
)


def _generation_for_prediction(session: Session, prediction_id: int) -> RecommendationGeneration | None:
    return session.scalar(select(RecommendationGeneration).where(RecommendationGeneration.prediction_id == prediction_id))


def audit_prediction_reproducibility(
    session: Session, prediction: Prediction, *, audited_at: datetime, currently_registered_provider_ids: tuple[str, ...] = ()
) -> ReproducibilityAuditDecision:
    """Idempotent by `(prediction_id, audited_at)`. `provider_drifted_
    categories` is only ever populated when `currently_registered_
    provider_ids` is actually supplied -- an empty/omitted set means
    "provider drift not checked this run," never "no drift found," so a
    caller who didn't check can't be misread as having confirmed
    reproducibility on that dimension."""
    existing = session.scalar(
        select(ReproducibilityAuditDecision).where(
            ReproducibilityAuditDecision.prediction_id == prediction.id, ReproducibilityAuditDecision.audited_at == audited_at,
        )
    )
    if existing is not None:
        return existing

    generation = _generation_for_prediction(session, prediction.id)
    trace = get_decision_trace(session, generation.id) if generation is not None else None

    version_drifted_fields: list[dict] = []
    provider_drifted_categories: list[dict] = []

    if trace is not None:
        for field_name, current_value in _VERSION_FIELD_CHECKS:
            traced_value = getattr(trace, field_name)
            if traced_value is not None and traced_value != current_value:
                version_drifted_fields.append({"field": field_name, "traced_value": traced_value, "current_value": current_value})

        if currently_registered_provider_ids:
            for item in trace.evidence_categories_snapshot:
                source = item.get("source")
                if source is not None and source not in currently_registered_provider_ids:
                    provider_drifted_categories.append({"category": item.get("category"), "traced_source": source})

    reproducible = trace is not None and not version_drifted_fields and not provider_drifted_categories

    decision = ReproducibilityAuditDecision(
        prediction_id=prediction.id, version_drifted_fields=version_drifted_fields,
        provider_drifted_categories=provider_drifted_categories, reproducible=reproducible,
        audited_at=audited_at, audit_rule_version=AUDIT_RULE_VERSION,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def get_reproducibility_audit_history(session: Session, prediction_id: int) -> tuple[ReproducibilityAuditDecision, ...]:
    return tuple(
        session.scalars(
            select(ReproducibilityAuditDecision).where(ReproducibilityAuditDecision.prediction_id == prediction_id).order_by(ReproducibilityAuditDecision.id.asc())
        ).all()
    )
