"""EPIC-M1.31: a hard evidence gate deciding whether a candidate model may
become production, consuming M1.30's disjoint-window comparison report as
its evidence -- never promoting based on training/in-sample performance
alone (non-goal): the gate's primary check is M1.30's own out-of-sample
`VALIDATED`/`REGRESSED`/`INSUFFICIENT_EVIDENCE` verdict, plus an additional
per-horizon regression check this EPIC adds on top (scope item 3, "no
unacceptable regression in any critical horizon" -- a candidate could pass
the overall verdict while quietly regressing one specific horizon, which the
overall success-rate delta alone would not catch).

Deliberately never deletes or overwrites a previous production version: the
append-only, immutable `model_promotions` log itself *is* the "current
production model" pointer (the most recent `PROMOTED` row) and the rollback
mechanism (every prior `PROMOTED` row remains queryable forever) -- "retain
the previous production model" and "make promotion atomic and reversible"
both fall out of one immutable insert per decision, not a separate
model-registry subsystem with its own consistency problem to solve.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .candidate_model_evaluation import REGRESSION_MARGIN, VERDICT_INSUFFICIENT_EVIDENCE, VERDICT_REGRESSED, CandidateModelComparisonReport
from .models import ModelPromotion

PROMOTION_RULE_VERSION = "PROM-001"

DECISION_PROMOTED = "PROMOTED"
DECISION_REJECTED = "REJECTED"

REASON_VALIDATED = "VALIDATED"
REASON_REGRESSED = "REGRESSED"
REASON_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
REASON_CRITICAL_HORIZON_REGRESSION = "CRITICAL_HORIZON_REGRESSION"


class ModelPromotionImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "candidate_model_version",
    "baseline_model_version",
    "evidence_report_version",
    "success_rate_delta",
    "decision",
    "decision_reason",
    "decided_at",
    "approver",
    "promotion_rule_version",
    "created_at",
)


@event.listens_for(ModelPromotion, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise ModelPromotionImmutableError(
            f"model promotion {target.id} field(s) {changed} cannot be modified after creation"
        )


def _critical_horizon_regressions(comparison: CandidateModelComparisonReport) -> tuple[str, ...]:
    baseline_by_horizon = {m.key: m for m in comparison.baseline.by_horizon}
    flagged = []
    for candidate_metric in comparison.candidate.by_horizon:
        baseline_metric = baseline_by_horizon.get(candidate_metric.key)
        if baseline_metric is None:
            continue
        if f"horizon:{candidate_metric.key}" in comparison.candidate.insufficient_sample_dimensions:
            continue
        if f"horizon:{candidate_metric.key}" in comparison.baseline.insufficient_sample_dimensions:
            continue
        if candidate_metric.success_rate is None or baseline_metric.success_rate is None:
            continue
        if candidate_metric.success_rate - baseline_metric.success_rate <= -REGRESSION_MARGIN:
            flagged.append(candidate_metric.key)
    return tuple(sorted(flagged))


def evaluate_promotion(
    session: Session,
    comparison: CandidateModelComparisonReport,
    *,
    candidate_model_version: str,
    baseline_model_version: str | None,
    approver: str,
    decided_at: datetime,
) -> ModelPromotion:
    """Deterministic function of `comparison` (AC: "promotion decision is
    reproducible from stored evidence") -- the same evidence always produces
    the same decision. Every candidate, promoted or rejected, gets an
    immutable audit row (AC: "failed candidates are retained as rejected
    versions with reasons")."""
    if comparison.verdict == VERDICT_INSUFFICIENT_EVIDENCE:
        decision, reason = DECISION_REJECTED, REASON_INSUFFICIENT_EVIDENCE
    elif comparison.verdict == VERDICT_REGRESSED:
        decision, reason = DECISION_REJECTED, REASON_REGRESSED
    elif _critical_horizon_regressions(comparison):
        decision, reason = DECISION_REJECTED, REASON_CRITICAL_HORIZON_REGRESSION
    else:
        decision, reason = DECISION_PROMOTED, REASON_VALIDATED

    promotion = ModelPromotion(
        candidate_model_version=candidate_model_version,
        baseline_model_version=baseline_model_version,
        evidence_report_version=comparison.version,
        success_rate_delta=comparison.success_rate_delta,
        decision=decision,
        decision_reason=reason,
        decided_at=decided_at,
        approver=approver,
        promotion_rule_version=PROMOTION_RULE_VERSION,
    )
    session.add(promotion)
    session.commit()
    session.refresh(promotion)
    return promotion


def get_current_production_model_version(session: Session) -> str | None:
    """The most recently promoted candidate is the current production
    model. Returns `None` if nothing has ever been promoted (bootstrap
    state) -- never fabricated."""
    latest = session.scalar(
        select(ModelPromotion)
        .where(ModelPromotion.decision == DECISION_PROMOTED)
        .order_by(ModelPromotion.id.desc())
    )
    return latest.candidate_model_version if latest is not None else None


def get_promotion_history(
    session: Session, *, candidate_model_version: str | None = None
) -> tuple[ModelPromotion, ...]:
    """Full, immutable, chronologically ordered promotion history -- this is
    the rollback mechanism: the previous production version is simply the
    prior `PROMOTED` row, never deleted."""
    query = select(ModelPromotion).order_by(ModelPromotion.id.asc())
    if candidate_model_version is not None:
        query = query.where(ModelPromotion.candidate_model_version == candidate_model_version)
    return tuple(session.scalars(query).all())
