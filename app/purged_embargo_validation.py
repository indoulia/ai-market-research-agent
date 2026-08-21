"""EPIC-M1.125: make time-overlapping financial labels and dependent
observations safe for model evaluation by enforcing purged and embargoed
validation policies (Lopez de Prado-style purged/embargoed cross-validation),
and make the resulting fold membership reconstructable for every experiment.

Reuses rather than reinvents:
1. **Window representation** -- M1.25's own `EvaluationWindow`
   (`app.out_of_sample_validation`) is reused unchanged for both a fold's
   training and validation windows; this module adds purge/embargo
   semantics on top of it, not a second window type.
2. **Leakage detection** -- M1.97's `BiasGuardCheck`/`is_effectively_passed`
   (`app.leakage_survivorship_guard`) already flags a specific prediction as
   unsafe for the `TRAINING` workflow; a training-fold candidate that fails
   that check is purged here too rather than re-deriving leakage signals.
3. **Holdout protection** -- M1.100's `HoldoutWindowRegistry`
   (`app.experiment_integrity_guard`) already records which windows are
   permanently reserved for one-time final evaluation; this module refuses
   to let any *other* fold's training or validation window touch a
   registered holdout window, so a walk-forward sweep can never consume it
   by accident.

A prediction's **label window** is `[as_of_timestamp, outcome resolution
timestamp]` -- the span during which its label depends on information not
yet known at `as_of_timestamp`. Any training-fold prediction whose label
window overlaps the (embargoed) validation window depends on the same
future information the validation fold is being scored on, and is purged.
Embargo extends that purge by `embargo_days` on both sides of the
validation window, guarding against the serial correlation typical of
financial time series (scope: "apply configurable embargo around
validation boundaries").

A prediction with no recorded outcome yet has an unknown label-window end
-- whether it would overlap validation cannot be determined, so it is
purged with `REASON_MISSING_OUTCOME` rather than optimistically included
(AC: "validation fails closed when temporal metadata is missing or
ambiguous"). A validation or training window itself must have explicit
`start` and `end` bounds for the same reason; both `generate_walk_forward_
folds` and `compute_purged_training_set` raise `AmbiguousValidationWindow
Error` rather than silently treating a missing bound as unbounded.

A holdout window purges matching training rows regardless of
`holdout_sanctioned_label` -- that parameter only permits *this* fold's
validation window to legitimately be the sanctioned one-time holdout
evaluation; it never makes holdout-period rows usable as training data
(AC: "final holdout data cannot be used for iterative tuning").

Same posture as M1.100's own `experiment_integrity_guard`: this module is a
propose-only pre-check. `evaluate_temporal_validation_policy`'s `verdict` is
the mandatory gate a promotion pipeline must consult (architectural rule:
"temporal validation policy is a mandatory platform gate ... not an
optional backtest configuration") -- but the actual promotion authority,
and the decision of *when* to consult it, remains exclusively M1.31/M1.44's,
mirroring every other decision module in this platform.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .leakage_survivorship_guard import WORKFLOW_TRAINING, get_bias_guard_history, get_override_for_check, is_effectively_passed
from .models import HoldoutWindowRegistry, Prediction, PredictionOutcome, TemporalValidationPolicyDecision, ValidationFold
from .out_of_sample_validation import EvaluationWindow

PURGED_EMBARGO_VERSION = "PEV-001"

# Fixed, documented, versioned policy constant (same convention as
# REGRESSION_MARGIN/WEAKNESS_MARGIN elsewhere in this platform): default
# buffer, in days, purged on both sides of a validation window.
DEFAULT_EMBARGO_DAYS = 2

REASON_MISSING_OUTCOME = "MISSING_OUTCOME_TIMESTAMP"
REASON_LABEL_WINDOW_OVERLAPS_VALIDATION = "LABEL_WINDOW_OVERLAPS_VALIDATION"
REASON_WITHIN_EMBARGO_PERIOD = "WITHIN_EMBARGO_PERIOD"
REASON_BIAS_GUARD_BLOCKED = "BIAS_GUARD_BLOCKED"
REASON_HOLDOUT_WINDOW_PROTECTED = "HOLDOUT_WINDOW_PROTECTED"

POLICY_VERDICT_PASS = "PASS"
POLICY_VERDICT_FAIL = "FAIL"

POLICY_FAIL_NO_FOLDS = "NO_FOLDS_EVALUATED"
POLICY_FAIL_EMPTY_TRAINING_SET = "FOLD_HAS_EMPTY_TRAINING_SET"

VALIDATION_FOLD_IMMUTABLE_FIELDS = (
    "model_version", "fold_index", "train_window_label", "train_window_start", "train_window_end",
    "validation_window_label", "validation_window_start", "validation_window_end", "embargo_days",
    "eligible_training_prediction_ids", "excluded_prediction_ids", "exclusion_reason_counts",
    "computed_at", "framework_version", "created_at",
)
POLICY_DECISION_IMMUTABLE_FIELDS = (
    "model_version", "fold_ids", "verdict", "fail_reasons", "evaluated_at", "policy_version", "created_at",
)


class AmbiguousValidationWindowError(RuntimeError):
    """A fold's train/validation window bounds must be fully explicit;
    validation fails closed rather than treating a missing bound as
    unbounded."""


class HoldoutContaminationError(RuntimeError):
    """Raised when a fold's validation window would overlap a
    M1.100-registered holdout window it is not the sanctioned one-time
    evaluation of."""


class ValidationFoldImmutableError(RuntimeError):
    pass


class TemporalValidationPolicyDecisionImmutableError(RuntimeError):
    pass


@event.listens_for(ValidationFold, "before_update")
def _reject_fold_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [f for f in VALIDATION_FOLD_IMMUTABLE_FIELDS if state.attrs[f].history.added or state.attrs[f].history.deleted]
    if changed:
        raise ValidationFoldImmutableError(f"validation fold {target.id} field(s) {changed} cannot be modified after creation")


@event.listens_for(TemporalValidationPolicyDecision, "before_update")
def _reject_policy_decision_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [f for f in POLICY_DECISION_IMMUTABLE_FIELDS if state.attrs[f].history.added or state.attrs[f].history.deleted]
    if changed:
        raise TemporalValidationPolicyDecisionImmutableError(
            f"temporal validation policy decision {target.id} field(s) {changed} cannot be modified after creation"
        )


@dataclass(frozen=True)
class LabelWindow:
    prediction_id: int
    information_timestamp: datetime
    outcome_timestamp: datetime | None


@dataclass(frozen=True)
class PurgeExclusion:
    prediction_id: int
    reason: str


@dataclass(frozen=True)
class PurgeResult:
    version: str
    train_window: EvaluationWindow
    validation_window: EvaluationWindow
    embargo_days: int
    eligible_training_prediction_ids: tuple[int, ...]
    excluded: tuple[PurgeExclusion, ...]


@dataclass(frozen=True)
class ValidationFoldPlan:
    fold_index: int
    train_window: EvaluationWindow
    validation_window: EvaluationWindow


def _require_bounded(window: EvaluationWindow) -> None:
    if window.start is None or window.end is None:
        raise AmbiguousValidationWindowError(f"window '{window.label}' must have explicit start and end bounds")


def _naive(value: datetime) -> datetime:
    """SQLite round-trips `DateTime(timezone=True)` values as naive, so a
    value read back from the DB and a caller-supplied aware value can't be
    compared directly; every comparison in this module goes through this
    first (same normalization M1.100's `register_holdout_window` uses)."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _intervals_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    a_start, a_end, b_start, b_end = _naive(a_start), _naive(a_end), _naive(b_start), _naive(b_end)
    return a_start <= b_end and b_start <= a_end


def get_label_windows(session: Session, prediction_ids: list[int]) -> tuple[LabelWindow, ...]:
    if not prediction_ids:
        return ()
    rows = session.execute(
        select(Prediction.id, Prediction.as_of_timestamp, PredictionOutcome.evaluation_date)
        .outerjoin(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .where(Prediction.id.in_(prediction_ids))
    ).all()
    return tuple(
        LabelWindow(prediction_id=prediction_id, information_timestamp=as_of, outcome_timestamp=evaluation_date)
        for prediction_id, as_of, evaluation_date in rows
    )


def generate_walk_forward_folds(
    *,
    universe_start: datetime,
    universe_end: datetime,
    train_span_days: int,
    validation_span_days: int,
    step_days: int,
    expanding: bool = False,
) -> tuple[ValidationFoldPlan, ...]:
    """Pure, deterministic fold generation (AC: "walk-forward evaluation is
    reproducible") -- no DB access, so the same arguments always produce the
    same fold boundaries. `expanding=True` grows the training window from
    `universe_start` on every fold instead of sliding it (an expanding-window
    scheme); `expanding=False` slides a fixed-width training window (a
    rolling walk-forward scheme). Every fold's validation window starts
    exactly where its training window ends."""
    if train_span_days <= 0 or validation_span_days <= 0 or step_days <= 0:
        raise AmbiguousValidationWindowError("train_span_days, validation_span_days and step_days must all be positive")
    if universe_end <= universe_start:
        raise AmbiguousValidationWindowError("universe_end must be after universe_start")

    folds: list[ValidationFoldPlan] = []
    fold_index = 0
    train_start = universe_start
    train_end = universe_start + timedelta(days=train_span_days)
    while True:
        validation_start = train_end
        validation_end = validation_start + timedelta(days=validation_span_days)
        if validation_end > universe_end:
            break
        folds.append(
            ValidationFoldPlan(
                fold_index=fold_index,
                train_window=EvaluationWindow(label=f"fold-{fold_index}-train", start=train_start, end=train_end),
                validation_window=EvaluationWindow(label=f"fold-{fold_index}-validation", start=validation_start, end=validation_end),
            )
        )
        fold_index += 1
        if not expanding:
            train_start = train_start + timedelta(days=step_days)
        train_end = train_end + timedelta(days=step_days)
    return tuple(folds)


def compute_purged_training_set(
    session: Session,
    *,
    train_window: EvaluationWindow,
    validation_window: EvaluationWindow,
    embargo_days: int = DEFAULT_EMBARGO_DAYS,
    holdout_sanctioned_label: str | None = None,
) -> PurgeResult:
    """Purge every training-window prediction whose label window overlaps
    the (embargoed) validation window, fails M1.97's `TRAINING`-workflow bias
    guard, or falls inside any M1.100-registered holdout window (AC: "final
    holdout data cannot be used for iterative tuning"). Fails closed
    (`AmbiguousValidationWindowError`) if either window lacks explicit
    bounds, purges rather than includes any candidate whose own outcome is
    not yet resolved, and raises `HoldoutContaminationError` if the
    validation window itself overlaps a holdout window other than
    `holdout_sanctioned_label`."""
    _require_bounded(train_window)
    _require_bounded(validation_window)
    if embargo_days < 0:
        raise AmbiguousValidationWindowError("embargo_days cannot be negative")

    embargo = timedelta(days=embargo_days)
    embargoed_start = validation_window.start - embargo
    embargoed_end = validation_window.end + embargo

    holdouts = tuple(
        h for h in session.scalars(select(HoldoutWindowRegistry)).all()
        if h.window_start is not None and h.window_end is not None
    )
    for holdout in holdouts:
        if holdout.label == holdout_sanctioned_label:
            continue
        if _intervals_overlap(validation_window.start, validation_window.end, holdout.window_start, holdout.window_end):
            raise HoldoutContaminationError(
                f"validation window '{validation_window.label}' overlaps registered holdout '{holdout.label}'; "
                f"pass holdout_sanctioned_label='{holdout.label}' if this IS the sanctioned one-time holdout evaluation"
            )

    candidate_ids = list(
        session.scalars(
            select(Prediction.id).where(
                Prediction.as_of_timestamp >= train_window.start,
                Prediction.as_of_timestamp <= train_window.end,
            )
        ).all()
    )
    label_windows = {lw.prediction_id: lw for lw in get_label_windows(session, candidate_ids)}

    eligible: list[int] = []
    excluded: list[PurgeExclusion] = []
    for prediction_id in candidate_ids:
        label_window = label_windows[prediction_id]
        if label_window.outcome_timestamp is None:
            excluded.append(PurgeExclusion(prediction_id, REASON_MISSING_OUTCOME))
            continue

        info_ts, outcome_ts = label_window.information_timestamp, label_window.outcome_timestamp

        if _intervals_overlap(info_ts, outcome_ts, validation_window.start, validation_window.end):
            excluded.append(PurgeExclusion(prediction_id, REASON_LABEL_WINDOW_OVERLAPS_VALIDATION))
            continue
        if _intervals_overlap(info_ts, outcome_ts, embargoed_start, embargoed_end):
            excluded.append(PurgeExclusion(prediction_id, REASON_WITHIN_EMBARGO_PERIOD))
            continue
        if any(_intervals_overlap(info_ts, outcome_ts, h.window_start, h.window_end) for h in holdouts):
            excluded.append(PurgeExclusion(prediction_id, REASON_HOLDOUT_WINDOW_PROTECTED))
            continue

        training_checks = [c for c in get_bias_guard_history(session, prediction_id) if c.workflow_type == WORKFLOW_TRAINING]
        if training_checks:
            latest_check = training_checks[-1]
            override = get_override_for_check(session, latest_check.id)
            if not is_effectively_passed(latest_check, override):
                excluded.append(PurgeExclusion(prediction_id, REASON_BIAS_GUARD_BLOCKED))
                continue

        eligible.append(prediction_id)

    return PurgeResult(
        version=PURGED_EMBARGO_VERSION,
        train_window=train_window,
        validation_window=validation_window,
        embargo_days=embargo_days,
        eligible_training_prediction_ids=tuple(eligible),
        excluded=tuple(excluded),
    )


def record_validation_fold(
    session: Session, *, model_version: str, fold_index: int, purge_result: PurgeResult, computed_at: datetime
) -> ValidationFold:
    """Idempotent by `(model_version, fold_index, computed_at)`: the
    immutable audit row a fold's training/validation membership is
    reconstructed from forever (AC: "training/validation membership can be
    reconstructed for every experiment")."""
    existing = session.scalar(
        select(ValidationFold).where(
            ValidationFold.model_version == model_version,
            ValidationFold.fold_index == fold_index,
            ValidationFold.computed_at == computed_at,
        )
    )
    if existing is not None:
        return existing

    reason_counts: dict[str, int] = {}
    for exclusion in purge_result.excluded:
        reason_counts[exclusion.reason] = reason_counts.get(exclusion.reason, 0) + 1

    fold = ValidationFold(
        model_version=model_version,
        fold_index=fold_index,
        train_window_label=purge_result.train_window.label,
        train_window_start=purge_result.train_window.start,
        train_window_end=purge_result.train_window.end,
        validation_window_label=purge_result.validation_window.label,
        validation_window_start=purge_result.validation_window.start,
        validation_window_end=purge_result.validation_window.end,
        embargo_days=purge_result.embargo_days,
        eligible_training_prediction_ids=list(purge_result.eligible_training_prediction_ids),
        excluded_prediction_ids=[e.prediction_id for e in purge_result.excluded],
        exclusion_reason_counts=reason_counts,
        computed_at=computed_at,
        framework_version=PURGED_EMBARGO_VERSION,
    )
    session.add(fold)
    session.commit()
    session.refresh(fold)
    return fold


def get_validation_folds(session: Session, model_version: str) -> tuple[ValidationFold, ...]:
    return tuple(
        session.scalars(
            select(ValidationFold).where(ValidationFold.model_version == model_version).order_by(ValidationFold.id.asc())
        ).all()
    )


def evaluate_temporal_validation_policy(
    session: Session, *, model_version: str, folds: tuple[ValidationFold, ...], evaluated_at: datetime
) -> TemporalValidationPolicyDecision:
    """The mandatory gate (architectural rule: "temporal validation policy is
    a mandatory platform gate ... not an optional backtest configuration") a
    promotion pipeline must consult before treating `model_version` as
    validated. `FAIL`s if no folds were evaluated at all, or if any fold's
    training set was purged down to nothing (a fold with zero eligible
    training rows proves nothing about generalization). Idempotent by
    `(model_version, evaluated_at)`."""
    existing = session.scalar(
        select(TemporalValidationPolicyDecision).where(
            TemporalValidationPolicyDecision.model_version == model_version,
            TemporalValidationPolicyDecision.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    fail_reasons: list[str] = []
    if not folds:
        fail_reasons.append(POLICY_FAIL_NO_FOLDS)
    else:
        for fold in folds:
            if len(fold.eligible_training_prediction_ids) == 0:
                fail_reasons.append(f"{POLICY_FAIL_EMPTY_TRAINING_SET}:{fold.fold_index}")

    verdict = POLICY_VERDICT_FAIL if fail_reasons else POLICY_VERDICT_PASS

    decision = TemporalValidationPolicyDecision(
        model_version=model_version,
        fold_ids=[f.id for f in folds],
        verdict=verdict,
        fail_reasons=fail_reasons,
        evaluated_at=evaluated_at,
        policy_version=PURGED_EMBARGO_VERSION,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def get_policy_decision_history(session: Session, model_version: str) -> tuple[TemporalValidationPolicyDecision, ...]:
    return tuple(
        session.scalars(
            select(TemporalValidationPolicyDecision)
            .where(TemporalValidationPolicyDecision.model_version == model_version)
            .order_by(TemporalValidationPolicyDecision.id.asc())
        ).all()
    )
