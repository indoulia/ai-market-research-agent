"""EPIC-M1.69: turn repeated, structured user feedback into testable
learning hypotheses and isolated experiments -- using M1.68's controlled
experiment framework rather than any bespoke mechanism.

Aggregation and recurrence detection are not reimplemented here: they are
M1.53's `compute_feedback_learning_signals`, whose `VERDICT_WEAK` already
means "this (category, reason_code) pattern's success rate is
statistically meaningfully below baseline, with at least
`MIN_SAMPLE_SIZE_FOR_COMPARISON` evaluated samples" (M1.16's own
threshold, reused unchanged). This module's only new contribution is
deciding *when* a weak signal has also been independently repeated by
more than one user (`repeated_prediction_count >= 1`) and, only then,
spinning up a real M1.68 `Experiment` with a `baseline`/`candidate` arm
pair to test it.

"One user's opinion cannot directly change production behavior" (AC)
holds doubly: this module has no write path to `Prediction`/
`ScanCandidate`/any scoring table (same structural guarantee M1.53 and
M1.68 already have), and `create_experiment_from_feedback_signal` refuses
to run at all unless the pattern was independently repeated by more than
one user on at least one prediction (`repeated_prediction_count >= 1`,
M1.53's own `REPEATED_PATTERN_MIN_DISTINCT_USERS` gate) -- a single
person's feedback, however strongly worded, can never reach this path.

"Keep feedback separate from objective outcomes" (scope): the
`FeedbackDrivenExperiment` link row stores only feedback-aggregate
provenance (which pattern, how much evidence) -- the actual experiment
metrics themselves are computed exclusively from objective
`Prediction`/`PredictionOutcome` history by M1.68's own
`run_experiment_arm`/`compare_experiment`, never from feedback text or
ratings.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .discovery_effectiveness import VERDICT_WEAK
from .feedback_learning_signals import FeedbackSignal, compute_feedback_learning_signals
from .models import FeedbackDrivenExperiment
from .out_of_sample_validation import EvaluationWindow
from .recommendation_experiments import add_experiment_arm, create_experiment

FEEDBACK_EXPERIMENT_PIPELINE_VERSION = "FEP-001"

ARM_BASELINE = "baseline"
ARM_CANDIDATE = "candidate"


class InsufficientFeedbackEvidenceError(ValueError):
    """Raised when a feedback signal has not been independently repeated
    by more than one user, or is not `VERDICT_WEAK` -- feedback patterns
    require minimum evidence before experimentation (AC)."""


class FeedbackDrivenExperimentImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "experiment_id",
    "feedback_category",
    "feedback_reason_code",
    "evaluated_count_at_creation",
    "distinct_user_count_at_creation",
    "repeated_prediction_count_at_creation",
    "success_rate_at_creation",
    "pipeline_version",
    "created_at",
)


@event.listens_for(FeedbackDrivenExperiment, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise FeedbackDrivenExperimentImmutableError(
            f"feedback-driven experiment link {target.id} field(s) {changed} cannot be modified after creation"
        )


def identify_recurring_feedback_patterns(session: Session) -> tuple[FeedbackSignal, ...]:
    """Detects statistically meaningful recurring feedback (scope item 2):
    a `VERDICT_WEAK` signal (M1.53's own out-of-baseline threshold) that
    was also independently repeated by more than one user on at least one
    prediction -- not just a single vocal user's own repeated complaints
    across many predictions."""
    report = compute_feedback_learning_signals(session)
    return tuple(
        signal
        for signal in report.signals
        if signal.verdict == VERDICT_WEAK and signal.repeated_prediction_count >= 1
    )


def _experiment_name_for_pattern(category: str, reason_code: str) -> str:
    return f"feedback-{category}-{reason_code}"


def get_experiment_link_for_pattern(
    session: Session, *, feedback_category: str, feedback_reason_code: str
) -> FeedbackDrivenExperiment | None:
    return session.execute(
        select(FeedbackDrivenExperiment).where(
            FeedbackDrivenExperiment.feedback_category == feedback_category,
            FeedbackDrivenExperiment.feedback_reason_code == feedback_reason_code,
        )
    ).scalar_one_or_none()


def create_experiment_from_feedback_signal(
    session: Session,
    signal: FeedbackSignal,
    *,
    model_version: str,
    baseline_window: EvaluationWindow,
    candidate_window: EvaluationWindow,
) -> FeedbackDrivenExperiment:
    """Creates an isolated M1.68 experiment testing whether `model_version`'s
    real-world performance differs between `baseline_window` and
    `candidate_window` -- the same "own model, two disjoint windows" shape
    M1.67 already validated -- and links it back to the feedback pattern
    that motivated it (AC: "every experiment identifies its feedback
    source and hypothesis"). Idempotent per (category, reason_code): a
    pattern that keeps recurring on later pipeline runs reuses its
    existing experiment rather than spawning a duplicate."""
    if signal.verdict != VERDICT_WEAK or signal.repeated_prediction_count < 1:
        raise InsufficientFeedbackEvidenceError(
            f"feedback pattern ({signal.category}, {signal.reason_code}) lacks sufficient repeated evidence "
            f"(verdict={signal.verdict}, repeated_prediction_count={signal.repeated_prediction_count})"
        )

    existing = get_experiment_link_for_pattern(
        session, feedback_category=signal.category, feedback_reason_code=signal.reason_code
    )
    if existing is not None:
        return existing

    experiment_name = _experiment_name_for_pattern(signal.category, signal.reason_code)
    hypothesis = (
        f"Recurring '{signal.reason_code}' feedback on category '{signal.category}' -- independently repeated "
        f"on {signal.repeated_prediction_count} prediction(s) by {signal.distinct_user_count} distinct users, "
        f"success rate {signal.success_rate} over {signal.evaluated_count} evaluated predictions -- may indicate "
        f"a real scoring or evidence weakness for model '{model_version}', worth testing across disjoint windows."
    )
    experiment = create_experiment(session, name=experiment_name, hypothesis=hypothesis)
    add_experiment_arm(
        session, experiment_id=experiment.id, arm_name=ARM_BASELINE, model_version=model_version, window=baseline_window
    )
    add_experiment_arm(
        session, experiment_id=experiment.id, arm_name=ARM_CANDIDATE, model_version=model_version, window=candidate_window
    )

    link = FeedbackDrivenExperiment(
        experiment_id=experiment.id,
        feedback_category=signal.category,
        feedback_reason_code=signal.reason_code,
        evaluated_count_at_creation=signal.evaluated_count,
        distinct_user_count_at_creation=signal.distinct_user_count,
        repeated_prediction_count_at_creation=signal.repeated_prediction_count,
        success_rate_at_creation=signal.success_rate,
        pipeline_version=FEEDBACK_EXPERIMENT_PIPELINE_VERSION,
    )
    session.add(link)
    session.commit()
    session.refresh(link)
    return link
