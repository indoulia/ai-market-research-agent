"""EPIC-M1.100: prevent MRA's self-learning system from selecting an
apparently superior model or strategy merely because many experiments
were tried against the same historical evidence, and prevent the final
holdout period from ever being reused for iterative tuning.

Deliberately does not reimplement an experiment registry: M1.68's own
`Experiment`/`ExperimentArm`/`ExperimentResult` (`app.recommendation_
experiments`) already registers every experiment before evaluation and
snapshots its config immutably -- this module only adds the three
capabilities that registry never had: (1) a holdout window that can be
consumed at most once, ever; (2) a trial-count-aware, multiplicity-
corrected significance check; (3) a requirement that a candidate's
apparent improvement independently replicate in a second, disjoint
window before it is treated as promotion-ready. None of this module
writes to `Experiment`/`ExperimentArm`/`ModelPromotion` -- it is a
propose-only pre-check, same posture as every other gate/decision module
in this platform; the actual promotion authority remains exclusively
M1.31/M1.44's.

`evaluate_multiplicity_adjusted_significance`'s correction is a simple,
fixed, documented Bonferroni-style scaling (`adjusted_margin =
WEAKNESS_MARGIN * trial_count`) -- not a fitted or learned statistic --
consistent with every other "fixed, documented, versioned policy
constant" in this codebase. `require_independent_confirmation` reuses
M1.25's own `VERDICT_VALIDATED`/`VERDICT_REGRESSED`/`VERDICT_
INSUFFICIENT_EVIDENCE` vocabulary and `REGRESSION_MARGIN`, applied twice
independently (once per disjoint window against the same baseline)
rather than inventing a second verdict vocabulary.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    ExperimentArm,
    HoldoutUsageRecord,
    HoldoutWindowRegistry,
    IndependentConfirmationDecision,
    MultiplicityGuardDecision,
    Prediction,
    PredictionOutcome,
)
from .out_of_sample_validation import (
    EvaluationWindow,
    OverlappingEvaluationWindowsError,
    REGRESSION_MARGIN,
    VERDICT_INSUFFICIENT_EVIDENCE,
    VERDICT_REGRESSED,
    VERDICT_VALIDATED,
)
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

EXPERIMENT_INTEGRITY_VERSION = "EIG-001"

VERDICT_SIGNIFICANT_AFTER_CORRECTION = "SIGNIFICANT_AFTER_CORRECTION"
VERDICT_NOT_SIGNIFICANT_AFTER_CORRECTION = "NOT_SIGNIFICANT_AFTER_CORRECTION"


class HoldoutRedefinitionError(RuntimeError):
    """A registered holdout window's bounds can never be changed."""


class UnknownHoldoutWindowError(RuntimeError):
    pass


class HoldoutAlreadyConsumedError(RuntimeError):
    """A holdout window may be used for evaluation at most once, ever."""


def register_holdout_window(
    session: Session, *, label: str, window: EvaluationWindow, registered_at: datetime
) -> HoldoutWindowRegistry:
    """Idempotent by `label`: re-registering the exact same bounds is a
    no-op; attempting to redefine an existing label's bounds raises
    (AC: "final holdout data cannot be used for iterative tuning" starts
    with the holdout's own definition never moving)."""
    def _naive(value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=None) if value is not None else None

    existing = session.scalar(select(HoldoutWindowRegistry).where(HoldoutWindowRegistry.label == label))
    if existing is not None:
        if _naive(existing.window_start) != _naive(window.start) or _naive(existing.window_end) != _naive(window.end):
            raise HoldoutRedefinitionError(f"holdout window '{label}' is already registered with different bounds")
        return existing

    registry = HoldoutWindowRegistry(
        label=label, window_start=window.start, window_end=window.end,
        registered_at=registered_at, registry_version=EXPERIMENT_INTEGRITY_VERSION,
    )
    session.add(registry)
    session.commit()
    session.refresh(registry)
    return registry


def get_holdout_window(session: Session, label: str) -> HoldoutWindowRegistry | None:
    return session.scalar(select(HoldoutWindowRegistry).where(HoldoutWindowRegistry.label == label))


def record_holdout_usage(
    session: Session, *, holdout_label: str, experiment_arm_id: int, used_at: datetime
) -> HoldoutUsageRecord:
    """Raises `HoldoutAlreadyConsumedError` if this holdout has ever been
    used before -- a real, DB-enforced one-time-use guarantee (unique
    constraint on `holdout_label`), not merely an application convention."""
    if get_holdout_window(session, holdout_label) is None:
        raise UnknownHoldoutWindowError(f"holdout window '{holdout_label}' was never registered")

    existing = session.scalar(select(HoldoutUsageRecord).where(HoldoutUsageRecord.holdout_label == holdout_label))
    if existing is not None:
        raise HoldoutAlreadyConsumedError(
            f"holdout window '{holdout_label}' was already consumed by experiment arm {existing.experiment_arm_id}"
        )

    usage = HoldoutUsageRecord(holdout_label=holdout_label, experiment_arm_id=experiment_arm_id, used_at=used_at)
    session.add(usage)
    session.commit()
    session.refresh(usage)
    return usage


def get_holdout_usage(session: Session, holdout_label: str) -> HoldoutUsageRecord | None:
    return session.scalar(select(HoldoutUsageRecord).where(HoldoutUsageRecord.holdout_label == holdout_label))


def count_trials_for_model_version(session: Session, model_version: str) -> int:
    """Every registered M1.68 `ExperimentArm` for this model version counts
    as one trial against shared historical evidence (scope: "track
    repeated trials against shared data")."""
    return len(list(session.scalars(select(ExperimentArm.id).where(ExperimentArm.model_version == model_version)).all()))


def evaluate_multiplicity_adjusted_significance(
    session: Session, *, model_version: str, observed_success_rate_delta: Decimal | None, evaluated_at: datetime
) -> MultiplicityGuardDecision:
    """Idempotent by `(model_version, evaluated_at)`. The more trials
    already registered for this model version, the larger the delta must
    be to count as significant -- a candidate cannot become 'apparently
    superior' merely by being tried many times (AC: "candidate selection
    accounts for repeated experimentation")."""
    existing = session.scalar(
        select(MultiplicityGuardDecision).where(
            MultiplicityGuardDecision.model_version == model_version,
            MultiplicityGuardDecision.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    trial_count = max(1, count_trials_for_model_version(session, model_version))
    adjusted_margin = WEAKNESS_MARGIN * Decimal(trial_count)
    significant = observed_success_rate_delta is not None and abs(observed_success_rate_delta) >= adjusted_margin
    verdict = VERDICT_SIGNIFICANT_AFTER_CORRECTION if significant else VERDICT_NOT_SIGNIFICANT_AFTER_CORRECTION

    decision = MultiplicityGuardDecision(
        model_version=model_version, trial_count=trial_count,
        observed_success_rate_delta=observed_success_rate_delta, weakness_margin=WEAKNESS_MARGIN,
        adjusted_margin=adjusted_margin, significant=significant, verdict=verdict,
        evaluated_at=evaluated_at, guard_rule_version=EXPERIMENT_INTEGRITY_VERSION,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def get_multiplicity_guard_history(session: Session, model_version: str) -> tuple[MultiplicityGuardDecision, ...]:
    return tuple(
        session.scalars(
            select(MultiplicityGuardDecision)
            .where(MultiplicityGuardDecision.model_version == model_version)
            .order_by(MultiplicityGuardDecision.id.asc())
        ).all()
    )


def _windows_overlap(a: EvaluationWindow, b: EvaluationWindow) -> bool:
    if a.end is not None and b.start is not None and a.end < b.start:
        return False
    if b.end is not None and a.start is not None and b.end < a.start:
        return False
    return True


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _model_scoped_success_rate(session: Session, model_version: str, window: EvaluationWindow) -> tuple[int, Decimal | None]:
    query = select(PredictionOutcome.outcome).join(Prediction, Prediction.id == PredictionOutcome.prediction_id).where(
        Prediction.model_version == model_version, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE"))
    )
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    outcomes = list(session.scalars(query).all())
    return len(outcomes), _rate(sum(1 for o in outcomes if o == "SUCCESS"), len(outcomes))


def _window_verdict(count: int, rate: Decimal | None, baseline_count: int, baseline_rate: Decimal | None) -> str:
    if count < MIN_SAMPLE_SIZE_FOR_COMPARISON or baseline_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or rate is None or baseline_rate is None:
        return VERDICT_INSUFFICIENT_EVIDENCE
    delta = rate - baseline_rate
    return VERDICT_REGRESSED if delta <= -REGRESSION_MARGIN else VERDICT_VALIDATED


def require_independent_confirmation(
    session: Session,
    *,
    model_version: str,
    baseline_window: EvaluationWindow,
    first_window: EvaluationWindow,
    confirmation_window: EvaluationWindow,
    confirmed_at: datetime,
) -> IndependentConfirmationDecision:
    """A candidate is only `both_validated` if its apparent improvement
    holds independently in TWO disjoint windows against the same
    baseline -- not just the one window that happened to look good (AC:
    "promotion requires independent evidence"). Raises
    `OverlappingEvaluationWindowsError` if any pair of the three windows
    overlaps -- a real independent replication requires disjoint
    evidence on all three. Idempotent by `(model_version, confirmed_at)`."""
    for a, b in ((baseline_window, first_window), (baseline_window, confirmation_window), (first_window, confirmation_window)):
        if _windows_overlap(a, b):
            raise OverlappingEvaluationWindowsError(f"windows '{a.label}' and '{b.label}' overlap")

    existing = session.scalar(
        select(IndependentConfirmationDecision).where(
            IndependentConfirmationDecision.model_version == model_version,
            IndependentConfirmationDecision.confirmed_at == confirmed_at,
        )
    )
    if existing is not None:
        return existing

    baseline_count, baseline_rate = _model_scoped_success_rate(session, model_version, baseline_window)
    first_count, first_rate = _model_scoped_success_rate(session, model_version, first_window)
    confirmation_count, confirmation_rate = _model_scoped_success_rate(session, model_version, confirmation_window)

    first_verdict = _window_verdict(first_count, first_rate, baseline_count, baseline_rate)
    confirmation_verdict = _window_verdict(confirmation_count, confirmation_rate, baseline_count, baseline_rate)
    both_validated = first_verdict == VERDICT_VALIDATED and confirmation_verdict == VERDICT_VALIDATED

    decision = IndependentConfirmationDecision(
        model_version=model_version, baseline_window_label=baseline_window.label,
        first_window_label=first_window.label, confirmation_window_label=confirmation_window.label,
        first_window_verdict=first_verdict, confirmation_window_verdict=confirmation_verdict,
        both_validated=both_validated, confirmed_at=confirmed_at,
        confirmation_rule_version=EXPERIMENT_INTEGRITY_VERSION,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def get_confirmation_history(session: Session, model_version: str) -> tuple[IndependentConfirmationDecision, ...]:
    return tuple(
        session.scalars(
            select(IndependentConfirmationDecision)
            .where(IndependentConfirmationDecision.model_version == model_version)
            .order_by(IndependentConfirmationDecision.id.asc())
        ).all()
    )
