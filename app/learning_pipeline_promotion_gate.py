"""EPIC-M1.57: the final safety gate deciding whether an M1.56 evidence-
backed adaptive-adjustment candidate may enter production recommendation
behavior.

Consumes M1.56's `AdaptiveAdjustmentCandidate` as its sole evidence input --
this gate never recomputes calibration/regime/feedback evidence itself, it
only judges what M1.56 already produced (the same "propose here, gate
there" split M1.29/M1.30 already have with M1.31, and M1.43 has with M1.44).
Reuses M1.16's `MIN_SAMPLE_SIZE_FOR_COMPARISON` as its own independent
minimum-evidence floor, rather than trusting M1.56's own internal gating
alone -- defense in depth.

Four mandatory checks, evaluated in order, any one of which blocks
promotion:
1. Sample size below `MIN_SAMPLE_SIZE_FOR_COMPARISON` -> `INSUFFICIENT_EVIDENCE`.
2. M1.56's own `validation_status` is `PENDING` (no out-of-sample check ever
   ran, or none was possible -- always true for feedback-sourced candidates
   today) -> `INSUFFICIENT_EVIDENCE`.
3. M1.56's own `validation_status` is `REJECTED` (did not improve
   out-of-sample) -> `FAIL`.
4. The candidate's own `expected_impact` magnitude exceeds
   `MAX_SAFE_EXPECTED_IMPACT` -- a proposed swing this large is treated as a
   regression/risk-metric concern regardless of how it validated on limited
   historical data (scope: "regression checks ... and risk metrics") ->
   `FAIL`.
5. Only if all four pass: `PASS`.

Append-only, immutable, PASS/FAIL/INSUFFICIENT_EVIDENCE decision log --
mirrors M1.31/M1.44's "the log is the pointer" pattern: `get_active_
promotion` returns the most recent `PASS` decision for a given
`(source_signal, affected_condition)`, and every prior decision remains
queryable forever via `get_promotion_history` (AC: "previous production
version remains available for rollback").

This module has no write path to `Prediction`, `ScanCandidate`, or any
scoring table at all -- "no candidate adjustment reaches production without
passing the gate" (AC) holds structurally: there is no other code path that
could act on an M1.56 candidate.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .adaptive_recommendation_adjustment import AdaptiveAdjustmentCandidate, STATUS_PENDING, STATUS_REJECTED, STATUS_VALIDATED
from .models import LearningPipelinePromotionDecision
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

GATE_RULE_VERSION = "LPG-001"

DECISION_PASS = "PASS"
DECISION_FAIL = "FAIL"
DECISION_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

REASON_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
REASON_NO_VALIDATION_EVIDENCE = "NO_VALIDATION_EVIDENCE"
REASON_NOT_IMPROVED_OUT_OF_SAMPLE = "NOT_IMPROVED_OUT_OF_SAMPLE"
REASON_RISK_METRIC_REGRESSION = "RISK_METRIC_REGRESSION"
REASON_VALIDATED = "VALIDATED"

# A proposed swing larger than this magnitude is treated as a safety-margin
# violation regardless of its own out-of-sample validation, since a change
# this large is inherently destabilizing on limited historical data. Fixed,
# documented, versioned -- not learned or fitted.
MAX_SAFE_EXPECTED_IMPACT = Decimal("0.30")


def evaluate_promotion(
    session: Session,
    candidate: AdaptiveAdjustmentCandidate,
    *,
    approver: str,
    decided_at: datetime,
) -> LearningPipelinePromotionDecision:
    """Deterministic function of `candidate`'s own fields (AC: "every
    promotion decision is reproducible and auditable") -- the same
    candidate always produces the same decision. Every candidate judged,
    passed or not, gets an immutable audit row."""
    if candidate.sample_size < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        decision, reason = DECISION_INSUFFICIENT_EVIDENCE, REASON_INSUFFICIENT_SAMPLE
    elif candidate.validation_status == STATUS_PENDING:
        decision, reason = DECISION_INSUFFICIENT_EVIDENCE, REASON_NO_VALIDATION_EVIDENCE
    elif candidate.validation_status == STATUS_REJECTED:
        decision, reason = DECISION_FAIL, REASON_NOT_IMPROVED_OUT_OF_SAMPLE
    elif candidate.expected_impact is not None and abs(candidate.expected_impact) > MAX_SAFE_EXPECTED_IMPACT:
        decision, reason = DECISION_FAIL, REASON_RISK_METRIC_REGRESSION
    else:
        assert candidate.validation_status == STATUS_VALIDATED
        decision, reason = DECISION_PASS, REASON_VALIDATED

    record = LearningPipelinePromotionDecision(
        source_signal=candidate.source_signal,
        affected_condition=candidate.affected_condition,
        candidate_version=candidate.version,
        sample_size=candidate.sample_size,
        expected_impact=candidate.expected_impact,
        decision=decision,
        decision_reason=reason,
        decided_at=decided_at,
        approver=approver,
        gate_rule_version=GATE_RULE_VERSION,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def get_active_promotion(
    session: Session, *, source_signal: str, affected_condition: str
) -> LearningPipelinePromotionDecision | None:
    """The most recent `PASS` decision for this exact `(source_signal,
    affected_condition)` is the active promotion (AC: "previous production
    version remains available for rollback" -- the prior `PASS` row is
    simply the previous rollback target, never deleted). Returns `None` if
    nothing has ever passed for this condition -- never fabricated."""
    return session.scalar(
        select(LearningPipelinePromotionDecision)
        .where(
            LearningPipelinePromotionDecision.source_signal == source_signal,
            LearningPipelinePromotionDecision.affected_condition == affected_condition,
            LearningPipelinePromotionDecision.decision == DECISION_PASS,
        )
        .order_by(LearningPipelinePromotionDecision.id.desc())
    )


def get_promotion_history(
    session: Session, *, source_signal: str | None = None
) -> tuple[LearningPipelinePromotionDecision, ...]:
    """Full, immutable, chronologically ordered decision history."""
    query = select(LearningPipelinePromotionDecision).order_by(LearningPipelinePromotionDecision.id.asc())
    if source_signal is not None:
        query = query.where(LearningPipelinePromotionDecision.source_signal == source_signal)
    return tuple(session.scalars(query).all())
