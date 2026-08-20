"""EPIC-M1.32: connect discovery effectiveness (M1.28), calibration
candidates (M1.29), candidate model evaluation (M1.30), and the promotion
gate (M1.31) into one repeatable, resumable, idempotent-in-effect cycle.

Deliberately composes existing EPICs' entry points wholesale rather than
reimplementing any of their logic -- this module's only genuinely new
behavior is the trigger ("has enough new evidence accumulated to be worth
re-evaluating?") and the audit log tying one cycle's refreshed report
versions to whatever promotion decision it did or didn't make.

The trigger is a simple, durable watermark: each `LearningCycle` row records
the highest `PredictionOutcome.id` it considered. `PredictionOutcome` rows
are themselves immutable and insert-only (M1.5), so id order is a valid,
monotonic proxy for "newer evidence than the last cycle saw." A cycle with
fewer new outcomes than `min_new_outcomes` is recorded as `SKIPPED` with an
explicit reason and does not touch the promotion gate at all -- "keep
production model/version stable when evidence is insufficient" (scope) holds
because nothing downstream of the trigger check ever runs.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .adaptive_calibration import build_calibration_candidate
from .candidate_model_evaluation import compare_candidate_model
from .discovery_effectiveness import compute_discovery_effectiveness_report
from .model_promotion import evaluate_promotion
from .models import LearningCycle, PredictionOutcome
from .out_of_sample_validation import EvaluationWindow

CYCLE_RULE_VERSION = "CLC-001"

DEFAULT_MIN_NEW_OUTCOMES = 20

OUTCOME_RAN = "RAN"
OUTCOME_SKIPPED = "SKIPPED"

SKIP_REASON_INSUFFICIENT_NEW_EVIDENCE = "INSUFFICIENT_NEW_EVIDENCE"


def _last_watermark(session: Session) -> int:
    latest = session.scalar(select(LearningCycle).order_by(LearningCycle.id.desc()))
    return latest.watermark_outcome_id if latest is not None else 0


def _current_max_outcome_id(session: Session) -> int:
    return session.scalar(select(func.max(PredictionOutcome.id))) or 0


def run_learning_cycle(
    session: Session,
    *,
    candidate_model_version: str,
    baseline_model_version: str | None,
    baseline_window: EvaluationWindow,
    candidate_window: EvaluationWindow,
    approver: str,
    started_at: datetime,
    min_new_outcomes: int = DEFAULT_MIN_NEW_OUTCOMES,
) -> LearningCycle:
    """Run one learning-cycle attempt. Resumable: the watermark this cycle
    advances to is exactly the current maximum `PredictionOutcome.id`, so a
    following cycle only ever counts genuinely new evidence, regardless of
    how many times this function has been called before (AC: "the learning
    cycle can run repeatedly without duplicate [promotion] effects"). Never
    rewrites a historical recommendation or outcome -- every write this
    function makes is a new, immutable row in `learning_cycles` (this
    module) or the tables M1.28/M1.29/M1.30/M1.31 already own."""
    last_watermark = _last_watermark(session)
    current_max = _current_max_outcome_id(session)
    new_outcomes_count = max(0, current_max - last_watermark)

    if new_outcomes_count < min_new_outcomes:
        cycle = LearningCycle(
            started_at=started_at,
            new_outcomes_count=new_outcomes_count,
            watermark_outcome_id=last_watermark,
            outcome=OUTCOME_SKIPPED,
            skip_reason=SKIP_REASON_INSUFFICIENT_NEW_EVIDENCE,
            discovery_effectiveness_version=None,
            calibration_candidate_version=None,
            candidate_model_evaluation_version=None,
            model_promotion_id=None,
            cycle_rule_version=CYCLE_RULE_VERSION,
        )
        session.add(cycle)
        session.commit()
        session.refresh(cycle)
        return cycle

    discovery_report = compute_discovery_effectiveness_report(session)
    calibration_candidate = build_calibration_candidate(session, candidate_window)
    comparison = compare_candidate_model(session, baseline=baseline_window, candidate=candidate_window)
    promotion = evaluate_promotion(
        session,
        comparison,
        candidate_model_version=candidate_model_version,
        baseline_model_version=baseline_model_version,
        approver=approver,
        decided_at=started_at,
    )

    cycle = LearningCycle(
        started_at=started_at,
        new_outcomes_count=new_outcomes_count,
        watermark_outcome_id=current_max,
        outcome=OUTCOME_RAN,
        skip_reason=None,
        discovery_effectiveness_version=discovery_report.report_version,
        calibration_candidate_version=calibration_candidate.version,
        candidate_model_evaluation_version=comparison.version,
        model_promotion_id=promotion.id,
        cycle_rule_version=CYCLE_RULE_VERSION,
    )
    session.add(cycle)
    session.commit()
    session.refresh(cycle)
    return cycle


def get_learning_cycle_history(session: Session) -> tuple[LearningCycle, ...]:
    """Full, immutable, chronologically ordered cycle history -- the basis
    for "the system can report what changed between learning cycles" (AC):
    a caller can diff consecutive rows' report versions and outcomes."""
    return tuple(session.scalars(select(LearningCycle).order_by(LearningCycle.id.asc())).all())
