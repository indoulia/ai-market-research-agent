"""EPIC-M1.45: connect discovery, recommendation outcomes, learning-dataset
construction (M1.39), candidate model comparison (M1.43), and the safe
promotion gate (M1.44) into one controlled, repeatable, resumable continuous
improvement loop -- the generalization of M1.32's exact same watermark-gated
cycle pattern to this newer chain of EPICs.

Deliberately composes existing EPICs' entry points wholesale rather than
reimplementing any of their logic. This module's only genuinely new behavior
is: the trigger ("has enough new evidence accumulated to be worth
re-evaluating?", reused unchanged from M1.32), rebuilding the M1.39 dataset
version for this cycle, invoking M1.43's comparison and M1.44's gate, and
(new in this EPIC) optionally triggering renewed discovery once the cycle has
actually run.

The trigger is the same simple, durable watermark M1.32 established: each
`SelfLearningCycle` row records the highest `PredictionOutcome.id` it
considered. `PredictionOutcome` rows are themselves immutable and insert-only
(M1.5), so id order is a valid, monotonic proxy for "newer evidence than the
last cycle saw." A cycle with fewer new outcomes than `min_new_outcomes` is
recorded as `SKIPPED` with an explicit reason and never touches the dataset,
comparison, or promotion gate at all -- "keep the current model when
evidence is insufficient" (scope) holds because nothing downstream of the
trigger check ever runs, matching the non-goal "guaranteed improvement" (this
loop only ever moves forward on real evidence, never on a schedule alone).

"Trigger renewed discovery using the active model" (scope) is implemented as
an optional, caller-supplied `trigger_discovery` callback -- this module
never calls any external service (ChatGPT, a live market feed) itself; the
concrete discovery mechanism (M1.17/M1.33) is wired by whatever caller owns
that decision, keeping this loop's own logic free of external-call cost or
failure modes it can't control. Discovery is triggered only after a cycle
actually ran (never on a `SKIPPED` cycle), regardless of the promotion
decision -- there is always an active model (newly promoted or the prior
one) to discover with.

"Failed learning cycles do not stop ordinary recommendation tracking" (AC)
holds structurally: this module is never called from, and has no dependency
edge into, the recommendation-generation pipeline (M1.12-M1.14) -- a failure
here cannot propagate there because there is no code path connecting them.
"Historical recommendations remain immutable" (AC) holds because this module
never writes to `Prediction`/`PredictionOutcome`/any table it doesn't own.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .candidate_model_comparison import ModelFunction, compare_candidate_model
from .continuous_learning import DEFAULT_MIN_NEW_OUTCOMES, OUTCOME_RAN, OUTCOME_SKIPPED, SKIP_REASON_INSUFFICIENT_NEW_EVIDENCE
from .historical_learning_dataset import build_learning_dataset
from .models import PredictionOutcome, SelfLearningCycle
from .safe_model_promotion import evaluate_promotion

CYCLE_RULE_VERSION = "CSL-001"


def _last_watermark(session: Session) -> int:
    latest = session.scalar(select(SelfLearningCycle).order_by(SelfLearningCycle.id.desc()))
    return latest.watermark_outcome_id if latest is not None else 0


def _current_max_outcome_id(session: Session) -> int:
    return session.scalar(select(func.max(PredictionOutcome.id))) or 0


def run_self_learning_cycle(
    session: Session,
    *,
    dataset_version: str,
    candidate_model: ModelFunction,
    candidate_model_name: str,
    approver: str,
    started_at: datetime,
    min_new_outcomes: int = DEFAULT_MIN_NEW_OUTCOMES,
    trigger_discovery: Callable[[], None] | None = None,
) -> SelfLearningCycle:
    """Run one self-learning-cycle attempt. Resumable: the watermark this
    cycle advances to is exactly the current maximum `PredictionOutcome.id`,
    so a following cycle only ever counts genuinely new evidence, regardless
    of how many times this function has been called before (AC: "the system
    can resume safely after interruption"). Every write this function makes
    is a new, immutable row in `self_learning_cycles` (this module) or the
    tables M1.39/M1.43/M1.44 already own -- never a rewrite of a historical
    recommendation or outcome."""
    last_watermark = _last_watermark(session)
    current_max = _current_max_outcome_id(session)
    new_outcomes_count = max(0, current_max - last_watermark)

    if new_outcomes_count < min_new_outcomes:
        cycle = SelfLearningCycle(
            started_at=started_at,
            new_outcomes_count=new_outcomes_count,
            watermark_outcome_id=last_watermark,
            outcome=OUTCOME_SKIPPED,
            skip_reason=SKIP_REASON_INSUFFICIENT_NEW_EVIDENCE,
            dataset_version=None,
            comparison_version=None,
            model_promotion_decision_id=None,
            discovery_triggered=False,
            cycle_rule_version=CYCLE_RULE_VERSION,
        )
        session.add(cycle)
        session.commit()
        session.refresh(cycle)
        return cycle

    build_learning_dataset(session, dataset_version=dataset_version)
    comparison = compare_candidate_model(
        session, dataset_version=dataset_version, candidate_model=candidate_model, candidate_model_name=candidate_model_name
    )
    promotion = evaluate_promotion(session, comparison, approver=approver, decided_at=started_at)

    discovery_triggered = False
    if trigger_discovery is not None:
        trigger_discovery()
        discovery_triggered = True

    cycle = SelfLearningCycle(
        started_at=started_at,
        new_outcomes_count=new_outcomes_count,
        watermark_outcome_id=current_max,
        outcome=OUTCOME_RAN,
        skip_reason=None,
        dataset_version=dataset_version,
        comparison_version=comparison.version,
        model_promotion_decision_id=promotion.id,
        discovery_triggered=discovery_triggered,
        cycle_rule_version=CYCLE_RULE_VERSION,
    )
    session.add(cycle)
    session.commit()
    session.refresh(cycle)
    return cycle


def get_self_learning_cycle_history(session: Session) -> tuple[SelfLearningCycle, ...]:
    """Full, immutable, chronologically ordered cycle history (AC: "every
    learning cycle has a unique version and audit record") -- a caller can
    trace any active-model change back to the exact comparison/promotion
    evidence that produced it (AC: "active model changes are traceable to
    comparison evidence")."""
    return tuple(session.scalars(select(SelfLearningCycle).order_by(SelfLearningCycle.id.asc())).all())
