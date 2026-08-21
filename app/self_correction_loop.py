"""EPIC-M1.88: close the loop between prediction outcomes, attribution and
usefulness evidence and controlled, evidence-based learning -- generating
explicit hypotheses about repeatable failure patterns, then requiring each
one to replicate in a later, disjoint out-of-sample monitoring window
before it is ever treated as a validated basis for reducing recommendation
eligibility.

Combines three already-immutable evidence sources, never recomputing any
of them: M1.5 `PredictionOutcome` (via M1.85's attribution snapshots),
M1.85 `PredictionAttributionSnapshot` (failure-pattern evidence), and
M1.86 `PredictionUsefulnessAssessment` (investment-usefulness evidence).
`generate_learning_hypotheses` reuses M1.25's own `EvaluationWindow`/
`OverlappingEvaluationWindowsError` -- the same disjoint-window abstraction
M1.29/M1.30/M1.40/M1.41/M1.43/M1.49/M1.67 already use -- rather than
inventing a second notion of "out of sample."

A hypothesis is only ever generated for a segment whose BASELINE window
already shows a real weakness (a failure association or a below-average
useful rate, both by the same `WEAKNESS_MARGIN` this platform already uses
everywhere else) -- there is no code path that manufactures a hypothesis
from a segment that looked fine in the baseline. Whether that hypothesis
is then treated as `VALIDATED` (the weakness replicated in the monitoring
window -- restrict eligibility) or `REJECTED` (it did not replicate --
restore/never restrict) is decided purely from the monitoring window's own
independent evidence. `PENDING_VALIDATION` (not enough monitoring-window
evidence yet) always resolves to `eligibility_effect=RESTORE`: the
Execution Rule's "prefer honest abstention... over increased prediction
volume" means an unconfirmed hypothesis may never restrict anything.

Every hypothesis row is an immutable, versioned, propose-only signal --
same posture as every other "propose here, gate there" module in this
platform (M1.65/M1.74/M1.77/M1.79/M1.80/M1.81/M1.83/M1.84/M1.87): this
module has no write path to `Prediction`, `ScanCandidate`, or any live
selection/eligibility table. Wiring `eligibility_effect` into the actual
recommendation feed remains a future deployment step, exactly like M1.84's
own `eligibility_reduced` before it. Recalculating trust itself is never
performed here either -- that remains M1.77's exclusive job, read fresh
each time by whatever future step wires this signal in.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .evidence_snapshot import ALL_EVIDENCE_CATEGORIES
from .models import LearningHypothesis, Prediction, PredictionAttributionSnapshot, PredictionUsefulnessAssessment
from .out_of_sample_validation import EvaluationWindow, OverlappingEvaluationWindowsError
from .prediction_attribution import DIMENSION_EVIDENCE_AVAILABLE, DIMENSION_HORIZON, DIMENSION_REGIME, DIMENSION_SMA20_DISTANCE, DIMENSION_VOLUME_RATIO
from .prediction_usefulness import USEFUL
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

HYPOTHESIS_RULE_VERSION = "SCL-001"

CATEGORY_FACTOR_FAILURE_PATTERN = "FACTOR_FAILURE_PATTERN"
CATEGORY_LOW_HORIZON_USEFULNESS = "LOW_HORIZON_USEFULNESS"

VALIDATION_PENDING = "PENDING_VALIDATION"
VALIDATION_VALIDATED = "VALIDATED"
VALIDATION_REJECTED = "REJECTED"

EFFECT_RESTRICT = "RESTRICT"
EFFECT_RESTORE = "RESTORE"

ACTION_REDUCE_HORIZON_ELIGIBILITY = "REDUCE_HORIZON_ELIGIBILITY"
ACTION_AVOID_REGIME_SEGMENT = "AVOID_REGIME_SEGMENT"
ACTION_RESTRICT_SEGMENT_ELIGIBILITY = "RESTRICT_SEGMENT_ELIGIBILITY"
ACTION_REQUIRE_EVIDENCE_CATEGORY = "REQUIRE_EVIDENCE_CATEGORY"

# Fixed, documented, versioned mapping from an attribution dimension to the
# candidate action a validated failure pattern on it would propose -- never
# learned or fitted.
_DIMENSION_TO_ACTION = {
    DIMENSION_HORIZON: ACTION_REDUCE_HORIZON_ELIGIBILITY,
    DIMENSION_REGIME: ACTION_AVOID_REGIME_SEGMENT,
    DIMENSION_SMA20_DISTANCE: ACTION_RESTRICT_SEGMENT_ELIGIBILITY,
    DIMENSION_VOLUME_RATIO: ACTION_RESTRICT_SEGMENT_ELIGIBILITY,
    DIMENSION_EVIDENCE_AVAILABLE: ACTION_REQUIRE_EVIDENCE_CATEGORY,
}


class LearningHypothesisImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "model_version",
    "hypothesis_category",
    "dimension",
    "factor_value",
    "baseline_window_label",
    "monitoring_window_label",
    "baseline_sample_count",
    "monitoring_sample_count",
    "baseline_rate",
    "monitoring_rate",
    "proposed_action",
    "validation_status",
    "eligibility_effect",
    "evidence_reference",
    "generated_at",
    "hypothesis_rule_version",
    "created_at",
)


@event.listens_for(LearningHypothesis, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise LearningHypothesisImmutableError(
            f"learning hypothesis {target.id} field(s) {changed} cannot be modified after creation"
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


def _dimension_values(snapshot: PredictionAttributionSnapshot) -> list[tuple[str, str]]:
    values = [
        (DIMENSION_HORIZON, str(snapshot.horizon_days)),
        (DIMENSION_SMA20_DISTANCE, snapshot.sma20_distance_bucket),
        (DIMENSION_VOLUME_RATIO, snapshot.volume_ratio_bucket),
    ]
    if snapshot.regime is not None:
        values.append((DIMENSION_REGIME, snapshot.regime))
    for category in ALL_EVIDENCE_CATEGORIES:
        available = category in snapshot.evidence_categories_available
        values.append((DIMENSION_EVIDENCE_AVAILABLE, f"{category}={'YES' if available else 'NO'}"))
    return [(dimension, value) for dimension, value in values if value is not None]


def _attribution_snapshots_in_window(
    session: Session, *, model_version: str, window: EvaluationWindow
) -> list[PredictionAttributionSnapshot]:
    query = select(PredictionAttributionSnapshot).where(PredictionAttributionSnapshot.model_version == model_version)
    if window.start is not None:
        query = query.where(PredictionAttributionSnapshot.snapshotted_at >= window.start)
    if window.end is not None:
        query = query.where(PredictionAttributionSnapshot.snapshotted_at <= window.end)
    return list(session.scalars(query).all())


def _factor_rates(snapshots: list[PredictionAttributionSnapshot]) -> dict[tuple[str, str], tuple[int, Decimal]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for snapshot in snapshots:
        for dimension, value in _dimension_values(snapshot):
            grouped.setdefault((dimension, value), []).append(snapshot.outcome)
    rates: dict[tuple[str, str], tuple[int, Decimal]] = {}
    for key, outcomes in grouped.items():
        rates[key] = (len(outcomes), _rate(sum(1 for o in outcomes if o == "SUCCESS"), len(outcomes)))
    return rates


def _usefulness_rates_by_horizon(
    session: Session, *, model_version: str, window: EvaluationWindow
) -> dict[str, tuple[int, Decimal]]:
    query = (
        select(Prediction.horizon_days, PredictionUsefulnessAssessment.usefulness_verdict)
        .join(PredictionUsefulnessAssessment, PredictionUsefulnessAssessment.prediction_id == Prediction.id)
        .where(Prediction.model_version == model_version)
    )
    if window.start is not None:
        query = query.where(PredictionUsefulnessAssessment.assessed_at >= window.start)
    if window.end is not None:
        query = query.where(PredictionUsefulnessAssessment.assessed_at <= window.end)
    rows = session.execute(query).all()

    grouped: dict[str, list[str]] = {}
    for horizon_days, verdict in rows:
        grouped.setdefault(str(horizon_days), []).append(verdict)
    rates: dict[str, tuple[int, Decimal]] = {}
    for horizon, verdicts in grouped.items():
        rates[horizon] = (len(verdicts), _rate(sum(1 for v in verdicts if v == USEFUL), len(verdicts)))
    return rates


def _validate_hypothesis(monitoring_lookup: dict, key) -> tuple[int, Decimal | None, str]:
    """Returns (monitoring_sample_count, monitoring_rate, validation_status).
    A weakness is `VALIDATED` only if it independently replicates in the
    monitoring window's own evidence; otherwise it is `REJECTED` (did not
    replicate) or `PENDING_VALIDATION` (not enough monitoring evidence yet
    to judge either way) -- never validated from the baseline alone."""
    monitoring_entry = monitoring_lookup.get(key)
    if monitoring_entry is None or monitoring_entry[0] < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        monitoring_count = 0 if monitoring_entry is None else monitoring_entry[0]
        return monitoring_count, None, VALIDATION_PENDING

    monitoring_count, monitoring_rate = monitoring_entry
    monitoring_overall_key = "__OVERALL__"
    monitoring_overall_rate = monitoring_lookup.get(monitoring_overall_key, (0, None))[1]
    if monitoring_overall_rate is None:
        return monitoring_count, monitoring_rate, VALIDATION_PENDING

    still_weak = (monitoring_overall_rate - monitoring_rate) >= WEAKNESS_MARGIN
    return monitoring_count, monitoring_rate, (VALIDATION_VALIDATED if still_weak else VALIDATION_REJECTED)


def generate_learning_hypotheses(
    session: Session,
    *,
    model_version: str,
    baseline_window: EvaluationWindow,
    monitoring_window: EvaluationWindow,
    generated_at: datetime,
) -> tuple[LearningHypothesis, ...]:
    """Idempotent per `(model_version, generated_at)`: once any hypothesis
    row exists for this exact generation run, that run's full result set
    (possibly empty) is the historical record and is never recomputed
    (AC-equivalent to every other immutable decision table in this
    platform)."""
    if _windows_overlap(baseline_window, monitoring_window):
        raise OverlappingEvaluationWindowsError(
            f"baseline window '{baseline_window.label}' and monitoring window '{monitoring_window.label}' overlap"
        )

    existing = session.scalars(
        select(LearningHypothesis).where(
            LearningHypothesis.model_version == model_version,
            LearningHypothesis.generated_at == generated_at,
        )
    ).all()
    if existing:
        return tuple(existing)

    rows: list[LearningHypothesis] = []

    # --- Factor failure-pattern hypotheses (M1.85 attribution evidence) ---
    baseline_snapshots = _attribution_snapshots_in_window(session, model_version=model_version, window=baseline_window)
    monitoring_snapshots = _attribution_snapshots_in_window(session, model_version=model_version, window=monitoring_window)
    baseline_factor_rates = _factor_rates(baseline_snapshots)
    monitoring_factor_rates = _factor_rates(monitoring_snapshots)
    baseline_overall_rate = _rate(sum(1 for s in baseline_snapshots if s.outcome == "SUCCESS"), len(baseline_snapshots))

    if baseline_overall_rate is not None:
        for (dimension, value), (count, rate) in sorted(baseline_factor_rates.items()):
            if count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
                continue
            if (baseline_overall_rate - rate) < WEAKNESS_MARGIN:
                continue

            monitoring_count, monitoring_rate, validation_status = _validate_hypothesis(
                {**monitoring_factor_rates, "__OVERALL__": (
                    len(monitoring_snapshots),
                    _rate(sum(1 for s in monitoring_snapshots if s.outcome == "SUCCESS"), len(monitoring_snapshots)),
                )},
                (dimension, value),
            )
            rows.append(LearningHypothesis(
                model_version=model_version, hypothesis_category=CATEGORY_FACTOR_FAILURE_PATTERN,
                dimension=dimension, factor_value=value,
                baseline_window_label=baseline_window.label, monitoring_window_label=monitoring_window.label,
                baseline_sample_count=count, monitoring_sample_count=monitoring_count,
                baseline_rate=rate, monitoring_rate=monitoring_rate,
                proposed_action=_DIMENSION_TO_ACTION.get(dimension, ACTION_RESTRICT_SEGMENT_ELIGIBILITY),
                validation_status=validation_status,
                eligibility_effect=(EFFECT_RESTRICT if validation_status == VALIDATION_VALIDATED else EFFECT_RESTORE),
                evidence_reference={"baseline_overall_rate": str(baseline_overall_rate)},
                generated_at=generated_at, hypothesis_rule_version=HYPOTHESIS_RULE_VERSION,
            ))

    # --- Low horizon-usefulness hypotheses (M1.86 usefulness evidence) ---
    baseline_usefulness = _usefulness_rates_by_horizon(session, model_version=model_version, window=baseline_window)
    monitoring_usefulness = _usefulness_rates_by_horizon(session, model_version=model_version, window=monitoring_window)
    baseline_all_counts = sum(count for count, _rate_ in baseline_usefulness.values())
    baseline_all_useful = sum(
        round(count * rate_) for count, rate_ in baseline_usefulness.values() if rate_ is not None
    )
    baseline_overall_useful_rate = _rate(baseline_all_useful, baseline_all_counts)

    if baseline_overall_useful_rate is not None:
        for horizon, (count, rate) in sorted(baseline_usefulness.items()):
            if count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
                continue
            if (baseline_overall_useful_rate - rate) < WEAKNESS_MARGIN:
                continue

            monitoring_all_counts = sum(c for c, _r in monitoring_usefulness.values())
            monitoring_all_useful = sum(
                round(c * r) for c, r in monitoring_usefulness.values() if r is not None
            )
            monitoring_count, monitoring_rate, validation_status = _validate_hypothesis(
                {**monitoring_usefulness, "__OVERALL__": (
                    monitoring_all_counts, _rate(monitoring_all_useful, monitoring_all_counts),
                )},
                horizon,
            )
            rows.append(LearningHypothesis(
                model_version=model_version, hypothesis_category=CATEGORY_LOW_HORIZON_USEFULNESS,
                dimension=DIMENSION_HORIZON, factor_value=horizon,
                baseline_window_label=baseline_window.label, monitoring_window_label=monitoring_window.label,
                baseline_sample_count=count, monitoring_sample_count=monitoring_count,
                baseline_rate=rate, monitoring_rate=monitoring_rate,
                proposed_action=ACTION_REDUCE_HORIZON_ELIGIBILITY,
                validation_status=validation_status,
                eligibility_effect=(EFFECT_RESTRICT if validation_status == VALIDATION_VALIDATED else EFFECT_RESTORE),
                evidence_reference={"baseline_overall_useful_rate": str(baseline_overall_useful_rate)},
                generated_at=generated_at, hypothesis_rule_version=HYPOTHESIS_RULE_VERSION,
            ))

    session.add_all(rows)
    session.commit()
    for row in rows:
        session.refresh(row)
    return tuple(rows)


def get_hypothesis_history(session: Session, *, model_version: str) -> tuple[LearningHypothesis, ...]:
    return tuple(
        session.scalars(
            select(LearningHypothesis)
            .where(LearningHypothesis.model_version == model_version)
            .order_by(LearningHypothesis.id.asc())
        ).all()
    )


def get_latest_eligibility_effect(
    session: Session, *, model_version: str, dimension: str, factor_value: str
) -> str | None:
    """The most recently generated hypothesis for this exact segment is the
    current recommendation -- a later run whose weakness no longer
    replicates naturally supersedes an earlier `RESTRICT` with `RESTORE`,
    without ever mutating the earlier, immutable row."""
    latest = session.scalar(
        select(LearningHypothesis)
        .where(
            LearningHypothesis.model_version == model_version,
            LearningHypothesis.dimension == dimension,
            LearningHypothesis.factor_value == factor_value,
        )
        .order_by(LearningHypothesis.generated_at.desc(), LearningHypothesis.id.desc())
    )
    return latest.eligibility_effect if latest is not None else None
