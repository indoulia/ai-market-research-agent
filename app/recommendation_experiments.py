"""EPIC-M1.68: an isolated, versioned framework for comparing recommendation
models, scoring rules, and evidence strategies without contaminating
production history.

An `Experiment` groups one or more `ExperimentArm`s -- each arm is a fully
explicit, stored configuration (model version, evaluation window, optional
horizon filter) describing which slice of already-evaluated production
recommendations to measure. Running an arm (`run_experiment_arm`) only ever
*reads* `Prediction`/`PredictionOutcome` (AC: "no experiment can mutate
production model state") and writes its computed metrics into a brand-new
`ExperimentResult` row -- experiment data never touches production tables
(scope: "keep experiment data separate from production outcomes").

"Comparison metrics use the same objective outcome definitions" (AC) holds
because accuracy is computed from the exact same `PredictionOutcome.outcome
in (SUCCESS, FAILURE)` definition M1.16/M1.25/M1.67 already use -- this
module does not invent a second notion of success.

"Results are reproducible from stored configuration" (AC): every
`ExperimentResult` snapshots the arm's config it was computed from
(`arm_config_snapshot`), and since the underlying evaluated-prediction
history is itself immutable and append-only, re-running the same arm config
against the same data always yields the same metrics -- proven directly by
`test_rerunning_an_arm_is_reproducible`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import math

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import Experiment, ExperimentArm, ExperimentResult, Prediction, PredictionOutcome
from .out_of_sample_validation import EvaluationWindow
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON

EXPERIMENT_FRAMEWORK_VERSION = "EXP-001"

VERDICT_READY = "READY"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


class DuplicateExperimentNameError(ValueError):
    """Raised when creating an experiment whose name already exists --
    experiments are isolated, named units; reusing a name would blur two
    distinct hypotheses together."""


class DuplicateExperimentArmNameError(ValueError):
    """Raised when adding an arm whose name already exists within the same
    experiment."""


class ExperimentImmutableError(RuntimeError):
    pass


class ExperimentArmImmutableError(RuntimeError):
    pass


EXPERIMENT_IMMUTABLE_FIELDS = ("name", "hypothesis", "experiment_version", "created_at")


@event.listens_for(Experiment, "before_update")
def _reject_experiment_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in EXPERIMENT_IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise ExperimentImmutableError(f"experiment {target.id} field(s) {changed} cannot be modified after creation")


EXPERIMENT_ARM_IMMUTABLE_FIELDS = (
    "experiment_id",
    "arm_name",
    "model_version",
    "window_label",
    "window_start",
    "window_end",
    "horizon_days_filter",
    "created_at",
)


@event.listens_for(ExperimentArm, "before_update")
def _reject_experiment_arm_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in EXPERIMENT_ARM_IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise ExperimentArmImmutableError(
            f"experiment arm {target.id} field(s) {changed} cannot be modified after creation"
        )


@dataclass(frozen=True)
class ArmComparisonEntry:
    arm_name: str
    result: ExperimentResult


@dataclass(frozen=True)
class ExperimentComparisonReport:
    framework_version: str
    experiment_id: int
    arms: tuple[ArmComparisonEntry, ...]
    best_arm_name: str | None


def create_experiment(session: Session, *, name: str, hypothesis: str) -> Experiment:
    existing = session.execute(select(Experiment).where(Experiment.name == name)).scalar_one_or_none()
    if existing is not None:
        raise DuplicateExperimentNameError(f"experiment name '{name}' already exists")

    experiment = Experiment(name=name, hypothesis=hypothesis, experiment_version=EXPERIMENT_FRAMEWORK_VERSION)
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    return experiment


def add_experiment_arm(
    session: Session,
    *,
    experiment_id: int,
    arm_name: str,
    model_version: str,
    window: EvaluationWindow,
    horizon_days_filter: int | None = None,
) -> ExperimentArm:
    existing = session.execute(
        select(ExperimentArm).where(ExperimentArm.experiment_id == experiment_id, ExperimentArm.arm_name == arm_name)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateExperimentArmNameError(f"arm name '{arm_name}' already exists for experiment {experiment_id}")

    arm = ExperimentArm(
        experiment_id=experiment_id,
        arm_name=arm_name,
        model_version=model_version,
        window_label=window.label,
        window_start=window.start,
        window_end=window.end,
        horizon_days_filter=horizon_days_filter,
    )
    session.add(arm)
    session.commit()
    session.refresh(arm)
    return arm


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _evaluated_rows_for_arm(session: Session, arm: ExperimentArm) -> list[tuple[Prediction, PredictionOutcome]]:
    query = select(Prediction, PredictionOutcome).join(
        PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id
    ).where(Prediction.model_version == arm.model_version, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    if arm.window_start is not None:
        query = query.where(Prediction.as_of_timestamp >= arm.window_start)
    if arm.window_end is not None:
        query = query.where(Prediction.as_of_timestamp <= arm.window_end)
    if arm.horizon_days_filter is not None:
        query = query.where(Prediction.horizon_days == arm.horizon_days_filter)
    return list(session.execute(query).all())


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values) / Decimal(len(values))


def _stdev(values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = float(_mean(values))
    variance = sum((float(v) - mean) ** 2 for v in values) / len(values)
    return Decimal(str(math.sqrt(variance)))


def _arm_config_snapshot(arm: ExperimentArm) -> dict:
    return {
        "model_version": arm.model_version,
        "window_label": arm.window_label,
        "window_start": arm.window_start.isoformat() if arm.window_start is not None else None,
        "window_end": arm.window_end.isoformat() if arm.window_end is not None else None,
        "horizon_days_filter": arm.horizon_days_filter,
    }


def run_experiment_arm(session: Session, arm_id: int, *, computed_at: datetime) -> ExperimentResult:
    """Reads production `Prediction`/`PredictionOutcome` rows only -- never
    writes to them (AC: "no experiment can mutate production model state").
    Below the shared evidence floor, every metric except `sample_count` is
    left `None` rather than drawing an unsafe conclusion from a small
    sample, matching the platform's established minimum-sample convention."""
    arm = session.get(ExperimentArm, arm_id)
    rows = _evaluated_rows_for_arm(session, arm)

    if len(rows) < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        result = ExperimentResult(
            experiment_arm_id=arm.id,
            sample_count=len(rows),
            accuracy=None,
            avg_return=None,
            avg_drawdown=None,
            calibration_error=None,
            consistency_stdev=None,
            verdict=VERDICT_INSUFFICIENT_SAMPLE,
            arm_config_snapshot=_arm_config_snapshot(arm),
            computed_at=computed_at,
            framework_version=EXPERIMENT_FRAMEWORK_VERSION,
        )
    else:
        success_count = sum(1 for _, o in rows if o.outcome == "SUCCESS")
        returns = [o.actual_return for _, o in rows]
        drawdowns = [o.maximum_drawdown for _, o in rows]
        calibration_errors = [
            abs(p.predicted_probability - (Decimal("1") if o.outcome == "SUCCESS" else Decimal("0")))
            for p, o in rows
        ]
        result = ExperimentResult(
            experiment_arm_id=arm.id,
            sample_count=len(rows),
            accuracy=_rate(success_count, len(rows)),
            avg_return=_mean(returns),
            avg_drawdown=_mean(drawdowns),
            calibration_error=_mean(calibration_errors),
            consistency_stdev=_stdev(returns),
            verdict=VERDICT_READY,
            arm_config_snapshot=_arm_config_snapshot(arm),
            computed_at=computed_at,
            framework_version=EXPERIMENT_FRAMEWORK_VERSION,
        )

    session.add(result)
    session.commit()
    session.refresh(result)
    return result


def get_arm_results(session: Session, arm_id: int) -> tuple[ExperimentResult, ...]:
    return tuple(
        session.scalars(
            select(ExperimentResult).where(ExperimentResult.experiment_arm_id == arm_id).order_by(ExperimentResult.id.asc())
        ).all()
    )


def compare_experiment(session: Session, experiment_id: int, *, computed_at: datetime) -> ExperimentComparisonReport:
    """Runs every arm belonging to `experiment_id` and reports them side by
    side, using the same objective outcome definition (accuracy) to pick a
    best arm among those with `VERDICT_READY` -- never among
    `INSUFFICIENT_SAMPLE` arms (AC: "small samples do not trigger unsafe
    conclusions")."""
    arms = session.scalars(
        select(ExperimentArm).where(ExperimentArm.experiment_id == experiment_id).order_by(ExperimentArm.id.asc())
    ).all()

    entries = tuple(
        ArmComparisonEntry(arm_name=arm.arm_name, result=run_experiment_arm(session, arm.id, computed_at=computed_at))
        for arm in arms
    )

    ready_entries = [entry for entry in entries if entry.result.verdict == VERDICT_READY]
    best_arm_name = max(ready_entries, key=lambda entry: entry.result.accuracy).arm_name if ready_entries else None

    return ExperimentComparisonReport(
        framework_version=EXPERIMENT_FRAMEWORK_VERSION,
        experiment_id=experiment_id,
        arms=entries,
        best_arm_name=best_arm_name,
    )
