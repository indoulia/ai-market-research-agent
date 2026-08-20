"""EPIC-M1.38: determine recommendation success/failure/neutral/insufficient-
data using predefined, immutable, versioned rules -- never subjective
interpretation.

Deliberately does not modify `app/outcomes.py` (M1.5): that module is the
foundational, heavily-tested source of the objective per-recommendation
result (target/stop-hit detection, realized return, invalid-data handling)
that a large fraction of this platform's already-merged EPICs depend on.
What M1.5's `PredictionOutcome` genuinely lacks -- and what this EPIC adds --
is an explicit, traceable classification *version* and a `NEUTRAL` category
distinct from a forced binary success/failure call: M1.5's own fallback (no
threshold hit) classifies purely by the sign of the actual return, even when
that return is negligibly close to zero. This module reclassifies that one
narrow case as `NEUTRAL` while leaving every other classification (target
hit, stop hit, unevaluable) exactly as M1.5 already determined it.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import OutcomeMeasurement, PredictionOutcome

MEASUREMENT_RULE_VERSION = "OMS-001"

OUTCOME_SUCCESS = "SUCCESS"
OUTCOME_FAILURE = "FAILURE"
OUTCOME_NEUTRAL = "NEUTRAL"
OUTCOME_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

# Fixed, documented, versioned policy constant: a realized return within this
# band of zero, when neither the target nor the stop was hit, is classified
# NEUTRAL rather than forced into SUCCESS or FAILURE by sign alone.
NEUTRAL_RETURN_BAND = Decimal("0.005")


class OutcomeMeasurementImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_outcome_id",
    "outcome_classification",
    "realized_return",
    "measured_at",
    "measurement_rule_version",
    "created_at",
)


@event.listens_for(OutcomeMeasurement, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise OutcomeMeasurementImmutableError(
            f"outcome measurement {target.id} field(s) {changed} cannot be modified after creation"
        )


def _classify(outcome: PredictionOutcome) -> str:
    if outcome.outcome == "UNEVALUABLE":
        return OUTCOME_INSUFFICIENT_DATA
    if outcome.target_hit:
        return OUTCOME_SUCCESS
    if outcome.stop_hit:
        return OUTCOME_FAILURE
    if abs(outcome.actual_return) <= NEUTRAL_RETURN_BAND:
        return OUTCOME_NEUTRAL
    return OUTCOME_SUCCESS if outcome.actual_return > 0 else OUTCOME_FAILURE


def measure_outcome(session: Session, outcome: PredictionOutcome, *, measured_at: datetime) -> OutcomeMeasurement:
    """Classify one already-final `PredictionOutcome` (scope: "freeze final
    outcome after sufficient evidence exists" -- this can only ever be
    called on a `PredictionOutcome` that itself only exists once M1.5 has
    already completed the horizon window). Deterministic and reproducible
    from stored data alone (AC): the same `outcome` row always yields the
    same classification. Idempotent by `prediction_outcome_id` uniqueness --
    re-measuring returns the original, immutable record (AC: "success/
    failure cannot be changed without a new versioned evaluation" -- a rule
    change would ship under a new `MEASUREMENT_RULE_VERSION`, producing a new
    row rather than mutating this one)."""
    existing = session.scalar(
        select(OutcomeMeasurement).where(OutcomeMeasurement.prediction_outcome_id == outcome.id)
    )
    if existing is not None:
        return existing

    classification = _classify(outcome)
    measurement = OutcomeMeasurement(
        prediction_outcome_id=outcome.id,
        outcome_classification=classification,
        realized_return=None if classification == OUTCOME_INSUFFICIENT_DATA else outcome.actual_return,
        measured_at=measured_at,
        measurement_rule_version=MEASUREMENT_RULE_VERSION,
    )
    session.add(measurement)
    session.commit()
    session.refresh(measurement)
    return measurement


def get_outcome_measurement(session: Session, prediction_outcome_id: int) -> OutcomeMeasurement | None:
    return session.scalar(
        select(OutcomeMeasurement).where(OutcomeMeasurement.prediction_outcome_id == prediction_outcome_id)
    )
