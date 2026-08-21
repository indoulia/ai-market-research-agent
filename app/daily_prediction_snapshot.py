"""EPIC-M1.78: capture the day-by-day market, evidence, model-input,
prediction and trust state required to reconstruct exactly what this
platform knew and predicted at each point in time.

`DailyPredictionSnapshot` is deliberately a thin, immutable *index* row,
not a duplicate of the data it points to: the point-in-time features,
evidence references, model/version, prediction, target, stop loss,
horizon, score, probability and confidence are all already captured,
immutably, by M1.66's `RecommendationDecisionTrace`; the trust state is
already captured, immutably, by M1.77's `PredictionTrustScore`. This
module only links a prediction to the correct trace and the correct
trust score *as of a given calendar day*, and never recomputes,
duplicates, or mutates either.

"Support intraday updates where configured while retaining end-of-day
canonical snapshots" (scope): `is_canonical` distinguishes the one
end-of-day snapshot for a `(prediction_id, snapshot_date)` pair from any
number of additional intraday snapshots for that same day -- only one
canonical snapshot is ever allowed per day (idempotent lookup-or-create),
while intraday snapshots are always freely appended. This platform's
real production cadence is one scan per calendar day (M1.12), so intraday
snapshots are a genuinely usable, forward-compatible capability rather
than something already exercised in production today -- the same honest
posture this platform has taken with every other forward-compatible
interface (e.g. M1.46's MEDIUM/LONG horizon bands).

"Retention does not silently delete active learning evidence" (AC) holds
the same way M1.37's archiving already does: nothing in this module ever
deletes or moves a row. `is_within_active_retention_window` is a purely
*derived* classification at query time over a fixed, documented,
versioned retention constant -- "retention" here means "eligible to be
excluded from a future archival query," never "actually removed."
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .decision_trace import get_decision_trace
from .models import DailyPredictionSnapshot, Prediction, PredictionTrustScore, RecommendationDecisionTrace, RecommendationGeneration
from .prediction_trust_score import get_trust_score_history

SNAPSHOT_RULE_VERSION = "DPS-001"

# Fixed, documented, versioned policy constant: a snapshot older than this
# is eligible for archival classification -- never actually deleted.
DEFAULT_SNAPSHOT_RETENTION_WINDOW = timedelta(days=730)


class DailyPredictionSnapshotImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "recommendation_decision_trace_id",
    "prediction_trust_score_id",
    "snapshot_date",
    "is_canonical",
    "snapshotted_at",
    "snapshot_rule_version",
    "created_at",
)


@event.listens_for(DailyPredictionSnapshot, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise DailyPredictionSnapshotImmutableError(
            f"daily prediction snapshot {target.id} field(s) {changed} cannot be modified after creation"
        )


@dataclass(frozen=True)
class SnapshotBundle:
    snapshot: DailyPredictionSnapshot
    decision_trace: RecommendationDecisionTrace | None
    trust_score: PredictionTrustScore | None


def _generation_for_prediction(session: Session, prediction_id: int) -> RecommendationGeneration | None:
    return session.scalar(select(RecommendationGeneration).where(RecommendationGeneration.prediction_id == prediction_id))


def _latest_trust_score_as_of(session: Session, prediction_id: int, as_of: datetime) -> PredictionTrustScore | None:
    naive_as_of = as_of.replace(tzinfo=None)
    history = get_trust_score_history(session, prediction_id)
    eligible = [s for s in history if s.computed_at.replace(tzinfo=None) <= naive_as_of]
    return eligible[-1] if eligible else None


def get_canonical_snapshot(session: Session, prediction_id: int, snapshot_date: date) -> DailyPredictionSnapshot | None:
    return session.scalar(
        select(DailyPredictionSnapshot).where(
            DailyPredictionSnapshot.prediction_id == prediction_id,
            DailyPredictionSnapshot.snapshot_date == snapshot_date,
            DailyPredictionSnapshot.is_canonical.is_(True),
        )
    )


def get_snapshot_history(session: Session, prediction_id: int) -> tuple[DailyPredictionSnapshot, ...]:
    return tuple(
        session.scalars(
            select(DailyPredictionSnapshot)
            .where(DailyPredictionSnapshot.prediction_id == prediction_id)
            .order_by(DailyPredictionSnapshot.id.asc())
        ).all()
    )


def capture_daily_prediction_snapshot(
    session: Session,
    prediction: Prediction,
    *,
    snapshot_date: date,
    snapshotted_at: datetime,
    is_canonical: bool = True,
) -> DailyPredictionSnapshot:
    """Links `prediction` to its already-captured M1.66 trace and the
    latest M1.77 trust score known as of `snapshotted_at` (point-in-time
    safe: a trust score computed later is never attached to an earlier
    snapshot). Idempotent for the canonical snapshot of a given day --
    calling again with `is_canonical=True` for a `(prediction_id,
    snapshot_date)` pair that already has one returns it unchanged
    (AC: "a new day's data never overwrites prior prediction history").
    Intraday (`is_canonical=False`) snapshots are always freely appended."""
    if is_canonical:
        existing = get_canonical_snapshot(session, prediction.id, snapshot_date)
        if existing is not None:
            return existing

    generation = _generation_for_prediction(session, prediction.id)
    trace = get_decision_trace(session, generation.id) if generation is not None else None
    trust_score = _latest_trust_score_as_of(session, prediction.id, snapshotted_at)

    snapshot = DailyPredictionSnapshot(
        prediction_id=prediction.id,
        recommendation_decision_trace_id=trace.id if trace is not None else None,
        prediction_trust_score_id=trust_score.id if trust_score is not None else None,
        snapshot_date=snapshot_date,
        is_canonical=is_canonical,
        snapshotted_at=snapshotted_at,
        snapshot_rule_version=SNAPSHOT_RULE_VERSION,
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def reconstruct_snapshot_bundle(session: Session, snapshot: DailyPredictionSnapshot) -> SnapshotBundle:
    """Joins one snapshot to its linked, already-immutable evidence (AC:
    "the system can reconstruct what data and model produced a past
    prediction") -- a pure read, no new computation."""
    trace = (
        session.get(RecommendationDecisionTrace, snapshot.recommendation_decision_trace_id)
        if snapshot.recommendation_decision_trace_id is not None
        else None
    )
    trust_score = (
        session.get(PredictionTrustScore, snapshot.prediction_trust_score_id)
        if snapshot.prediction_trust_score_id is not None
        else None
    )
    return SnapshotBundle(snapshot=snapshot, decision_trace=trace, trust_score=trust_score)


def is_within_active_retention_window(
    snapshot: DailyPredictionSnapshot, *, as_of: datetime, retention_window: timedelta = DEFAULT_SNAPSHOT_RETENTION_WINDOW
) -> bool:
    """A purely derived classification -- never deletes or moves
    anything (AC: "retention does not silently delete active learning
    evidence"; every snapshot remains queryable regardless of this
    function's result)."""
    age = as_of.replace(tzinfo=None) - snapshot.snapshotted_at.replace(tzinfo=None)
    return age <= retention_window
