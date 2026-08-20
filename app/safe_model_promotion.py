"""EPIC-M1.44: a hard evidence gate deciding whether a candidate model may
become the active model, consuming M1.43's same-period comparison report as
its sole evidence -- the natural generalization of M1.31 (which gated M1.30's
same-model/two-period comparison) to M1.43's two-model/same-period one.

The gate has three mandatory checks, evaluated in order, any one of which
rejects:
1. M1.43's own `VERDICT_INSUFFICIENT_EVIDENCE` -> `REASON_INSUFFICIENT_EVIDENCE`
   (scope: "require minimum sample sizes", inherited from M1.43's own
   `MIN_SAMPLE_SIZE_FOR_COMPARISON` gating, not redefined).
2. M1.43's own `VERDICT_REGRESSED` -> `REASON_REGRESSED` (scope: "require
   candidate-vs-current comparison evidence" -- M1.43's overall calibration
   verdict *is* that check; this gate consumes it, never recomputes it).
3. **New in this EPIC, generalizing M1.31's single horizon-only check**: a
   candidate could pass the overall verdict while quietly regressing one
   specific horizon, sector, market-cap bucket, discovery source, or regime
   it wasn't dominant in. `_critical_segment_regressions` scans every segment
   bucket present in both models' evaluations across all five of M1.43's own
   dimensions (skipping any bucket either side already flagged
   `INSUFFICIENT_SAMPLE`) and rejects with `REASON_CRITICAL_SEGMENT_REGRESSION`
   if any bucket's calibration error worsens by `REGRESSION_MARGIN` (reused
   from M1.30/M1.43, not redefined) or more.

Deliberately never deletes or overwrites a prior decision: the append-only,
immutable `model_promotion_decisions` log itself *is* the "active model"
pointer (the most recent `PROMOTED` row for a dataset version) and the
rollback mechanism (every prior `PROMOTED` row remains queryable forever) --
mirroring M1.31's exact design so "version active model selection" and
"support rollback to the previous approved model" both fall out of one
immutable insert per decision, never a second model-registry subsystem.

This module has no code path that writes to `Prediction`, `PredictionOutcome`,
or any other historical-result table -- promotion cannot modify historical
recommendation results (AC) because there is nothing here that could.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .candidate_model_comparison import CandidateModelComparisonReport, VERDICT_INSUFFICIENT_EVIDENCE, VERDICT_REGRESSED
from .candidate_model_evaluation import REGRESSION_MARGIN
from .models import ModelPromotionDecision

PROMOTION_RULE_VERSION = "SMP-001"

DECISION_PROMOTED = "PROMOTED"
DECISION_REJECTED = "REJECTED"

REASON_VALIDATED = "VALIDATED"
REASON_REGRESSED = "REGRESSED"
REASON_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
REASON_CRITICAL_SEGMENT_REGRESSION = "CRITICAL_SEGMENT_REGRESSION"


class ModelPromotionDecisionImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "dataset_version",
    "candidate_model_name",
    "comparison_version",
    "calibration_error_delta",
    "decision",
    "decision_reason",
    "regressed_segment_dimension",
    "regressed_segment_key",
    "decided_at",
    "approver",
    "promotion_rule_version",
    "created_at",
)


@event.listens_for(ModelPromotionDecision, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise ModelPromotionDecisionImmutableError(
            f"model promotion decision {target.id} field(s) {changed} cannot be modified after creation"
        )


def _all_segment_metrics(evaluation) -> tuple:
    return (
        evaluation.by_horizon
        + evaluation.by_sector
        + evaluation.by_market_cap_bucket
        + evaluation.by_discovery_source
        + evaluation.by_regime
    )


def _critical_segment_regressions(comparison: CandidateModelComparisonReport) -> tuple[tuple[str, str], ...]:
    production_by_key = {(m.dimension, m.key): m for m in _all_segment_metrics(comparison.production)}
    candidate_by_key = {(m.dimension, m.key): m for m in _all_segment_metrics(comparison.candidate)}
    insufficient = set(comparison.production.insufficient_sample_dimensions) | set(
        comparison.candidate.insufficient_sample_dimensions
    )

    regressions = []
    for key in sorted(set(production_by_key) & set(candidate_by_key)):
        dimension, bucket_key = key
        if f"{dimension}:{bucket_key}" in insufficient:
            continue
        production_metric = production_by_key[key]
        candidate_metric = candidate_by_key[key]
        if (
            production_metric.mean_absolute_calibration_error is None
            or candidate_metric.mean_absolute_calibration_error is None
        ):
            continue
        delta = candidate_metric.mean_absolute_calibration_error - production_metric.mean_absolute_calibration_error
        if delta >= REGRESSION_MARGIN:
            regressions.append(key)
    return tuple(regressions)


def evaluate_promotion(
    session: Session,
    comparison: CandidateModelComparisonReport,
    *,
    approver: str,
    decided_at: datetime,
) -> ModelPromotionDecision:
    """Deterministic function of `comparison` (AC: "every promotion/rejection
    is auditable" and reproducible from stored evidence) -- the same evidence
    always produces the same decision. Every candidate, promoted or rejected,
    gets an immutable audit row (AC: "provide explicit rejection reasons")."""
    if comparison.verdict == VERDICT_INSUFFICIENT_EVIDENCE:
        decision, reason, dimension, key = DECISION_REJECTED, REASON_INSUFFICIENT_EVIDENCE, None, None
    elif comparison.verdict == VERDICT_REGRESSED:
        decision, reason, dimension, key = DECISION_REJECTED, REASON_REGRESSED, None, None
    else:
        regressions = _critical_segment_regressions(comparison)
        if regressions:
            dimension, key = regressions[0]
            decision, reason = DECISION_REJECTED, REASON_CRITICAL_SEGMENT_REGRESSION
        else:
            decision, reason, dimension, key = DECISION_PROMOTED, REASON_VALIDATED, None, None

    record = ModelPromotionDecision(
        dataset_version=comparison.dataset_version,
        candidate_model_name=comparison.candidate.model_name,
        comparison_version=comparison.version,
        calibration_error_delta=comparison.calibration_error_delta,
        decision=decision,
        decision_reason=reason,
        regressed_segment_dimension=dimension,
        regressed_segment_key=key,
        decided_at=decided_at,
        approver=approver,
        promotion_rule_version=PROMOTION_RULE_VERSION,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def get_active_model(session: Session, *, dataset_version: str) -> ModelPromotionDecision | None:
    """The most recently promoted candidate for `dataset_version` is the
    active model (AC: "active model version is unambiguous"). Returns `None`
    if nothing has ever been promoted for this dataset version (bootstrap
    state) -- never fabricated."""
    return session.scalar(
        select(ModelPromotionDecision)
        .where(ModelPromotionDecision.dataset_version == dataset_version, ModelPromotionDecision.decision == DECISION_PROMOTED)
        .order_by(ModelPromotionDecision.id.desc())
    )


def get_promotion_history(
    session: Session, *, candidate_model_name: str | None = None
) -> tuple[ModelPromotionDecision, ...]:
    """Full, immutable, chronologically ordered decision history -- this is
    the rollback mechanism: the previous active model is simply the prior
    `PROMOTED` row for that dataset version, never deleted (AC: "previous
    model remains recoverable for rollback")."""
    query = select(ModelPromotionDecision).order_by(ModelPromotionDecision.id.asc())
    if candidate_model_name is not None:
        query = query.where(ModelPromotionDecision.candidate_model_name == candidate_model_name)
    return tuple(session.scalars(query).all())
