"""EPIC-M1.97: make look-ahead, survivorship and selection bias detectable
and blocking for training, replay and evaluation workflows specifically
-- a different consumer than M1.81's live recommendation gate.

This platform already has three real, independent signals this module
composes rather than duplicates:

1. **Look-ahead leakage** -- M1.74's `EvidenceQualityDecision.state ==
   STATE_LEAKAGE_DETECTED` (future-dated evidence relative to
   `as_of_timestamp`).
2. **Post-decision data revision** -- M1.62's `RecommendationRevalidationOutcome`
   history; an `UPDATED`/`WITHDRAWN` outcome means the evidence this
   prediction rested on was later found materially different, which a
   training/replay/evaluation workflow must not silently treat as still
   valid.
3. **Unverified universe membership / selection-bias risk** -- every
   genuine `Prediction` in this platform is produced by `app.discovery.
   route_discovery_through_pipeline`, which always creates a
   `RecommendationGeneration` linking it back to the `ScanCandidate` (and
   therefore the `DailyCandidateScan`, and that scan's own recorded
   `universe_version`/`scan_date`) it came from. A prediction with no such
   link was not selected through the platform's real, point-in-time,
   unbiased daily scan -- exactly the shape a hand-picked or backfilled
   "looks-good" row injected directly into a training set would have.

**Survivorship bias was already structurally absent** before this EPIC
(verified by M1.96's own grep audit: no historical report anywhere
filters by `Stock.is_active`, and nothing ever deletes a `Stock` row) --
`test_delisted_stocks_prediction_still_passes_the_guard` proves this
guard does not itself introduce one either.

**Never rewrites, never silently bypasses** (AC: "overrides require
explicit, auditable justification and cannot silently bypass production
gates"): a `BiasGuardCheck` is immutable once recorded. Overriding a
`BLOCKED` verdict requires a separate, mandatory-justification
`BiasGuardOverride` row referencing it -- the original `BLOCKED` verdict
is never edited or hidden; `is_effectively_passed` is the one function a
caller should use to ask "can I actually use this," and it only returns
`True` for a `BLOCKED` check when a real override row exists.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .evidence_quality_gate import STATE_LEAKAGE_DETECTED, get_quality_decision_history
from .models import BiasGuardCheck, BiasGuardOverride, Prediction, RecommendationGeneration
from .recommendation_revalidation import OUTCOME_UPDATED, OUTCOME_WITHDRAWN, get_revalidation_history

BIAS_GUARD_VERSION = "BSG-001"

CHECK_IMMUTABLE_FIELDS = (
    "prediction_id", "workflow_type", "verdict", "reason_codes", "evidence",
    "checked_at", "guard_rule_version", "created_at",
)
OVERRIDE_IMMUTABLE_FIELDS = (
    "check_id", "justification", "authorized_by", "recorded_at", "override_version", "created_at",
)

WORKFLOW_TRAINING = "TRAINING"
WORKFLOW_REPLAY = "REPLAY"
WORKFLOW_EVALUATION = "EVALUATION"
ALL_WORKFLOW_TYPES = (WORKFLOW_TRAINING, WORKFLOW_REPLAY, WORKFLOW_EVALUATION)

VERDICT_PASS = "PASS"
VERDICT_BLOCKED = "BLOCKED"

REASON_LEAKAGE_DETECTED = "LEAKAGE_DETECTED"
REASON_POST_DECISION_REVISION = "POST_DECISION_REVISION"
REASON_UNVERIFIED_UNIVERSE_MEMBERSHIP = "UNVERIFIED_UNIVERSE_MEMBERSHIP"

_REVISION_OUTCOMES = (OUTCOME_UPDATED, OUTCOME_WITHDRAWN)


class InvalidBiasGuardWorkflowError(ValueError):
    pass


class InvalidOverrideError(ValueError):
    pass


class OverrideAlreadyRecordedError(RuntimeError):
    pass


class BiasGuardCheckImmutableError(RuntimeError):
    pass


class BiasGuardOverrideImmutableError(RuntimeError):
    pass


@event.listens_for(BiasGuardCheck, "before_update")
def _reject_check_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [f for f in CHECK_IMMUTABLE_FIELDS if state.attrs[f].history.added or state.attrs[f].history.deleted]
    if changed:
        raise BiasGuardCheckImmutableError(f"bias guard check {target.id} field(s) {changed} cannot be modified after creation")


@event.listens_for(BiasGuardOverride, "before_update")
def _reject_override_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [f for f in OVERRIDE_IMMUTABLE_FIELDS if state.attrs[f].history.added or state.attrs[f].history.deleted]
    if changed:
        raise BiasGuardOverrideImmutableError(f"bias guard override {target.id} field(s) {changed} cannot be modified after creation")


def _detect_leakage(session: Session, prediction_id: int) -> list[str] | None:
    history = get_quality_decision_history(session, prediction_id)
    if not history:
        return None
    latest = history[-1]
    if latest.state == STATE_LEAKAGE_DETECTED:
        return list(latest.leaked_categories)
    return None


def _detect_post_decision_revision(session: Session, prediction_id: int) -> list[str]:
    history = get_revalidation_history(session, prediction_id)
    return [outcome.outcome for outcome in history if outcome.outcome in _REVISION_OUTCOMES]


def _has_verified_universe_membership(session: Session, prediction_id: int) -> bool:
    """A genuine platform-produced prediction always has a
    `RecommendationGeneration` row linking it back to the `ScanCandidate`
    (and therefore the `DailyCandidateScan`) it was discovered through.
    Its absence is the one real, checkable signal that a row entered a
    training/replay/evaluation dataset by some path other than the
    platform's real, unbiased daily universe scan."""
    return (
        session.scalar(
            select(RecommendationGeneration.id).where(RecommendationGeneration.prediction_id == prediction_id)
        )
        is not None
    )


def run_bias_guard_check(
    session: Session, prediction: Prediction, *, workflow_type: str, checked_at: datetime
) -> BiasGuardCheck:
    """Deterministic given whatever M1.62/M1.74/M1.13 history already
    exists for `prediction` (AC: "leakage checks run automatically before
    validation/training" implies this must be cheap and safe to call on
    every candidate row). Idempotent by `(prediction_id, workflow_type,
    checked_at)`, mirroring M1.74's own idempotency convention."""
    if workflow_type not in ALL_WORKFLOW_TYPES:
        raise InvalidBiasGuardWorkflowError(f"workflow_type must be one of {ALL_WORKFLOW_TYPES}, got {workflow_type!r}")

    existing = session.scalar(
        select(BiasGuardCheck).where(
            BiasGuardCheck.prediction_id == prediction.id,
            BiasGuardCheck.workflow_type == workflow_type,
            BiasGuardCheck.checked_at == checked_at,
        )
    )
    if existing is not None:
        return existing

    reason_codes: list[str] = []
    evidence: dict = {}

    leaked_categories = _detect_leakage(session, prediction.id)
    if leaked_categories is not None:
        reason_codes.append(REASON_LEAKAGE_DETECTED)
        evidence["leaked_categories"] = leaked_categories

    revision_outcomes = _detect_post_decision_revision(session, prediction.id)
    if revision_outcomes:
        reason_codes.append(REASON_POST_DECISION_REVISION)
        evidence["revalidation_outcomes"] = revision_outcomes

    if not _has_verified_universe_membership(session, prediction.id):
        reason_codes.append(REASON_UNVERIFIED_UNIVERSE_MEMBERSHIP)

    verdict = VERDICT_BLOCKED if reason_codes else VERDICT_PASS

    check = BiasGuardCheck(
        prediction_id=prediction.id,
        workflow_type=workflow_type,
        verdict=verdict,
        reason_codes=reason_codes,
        evidence=evidence,
        checked_at=checked_at,
        guard_rule_version=BIAS_GUARD_VERSION,
    )
    session.add(check)
    session.commit()
    session.refresh(check)
    return check


def record_bias_guard_override(
    session: Session, check: BiasGuardCheck, *, justification: str, authorized_by: str, recorded_at: datetime
) -> BiasGuardOverride:
    """A `BLOCKED` verdict is never edited (AC: "cannot silently bypass
    production gates") -- overriding it means recording this separate,
    permanent, mandatory-justification row instead. Raises rather than
    allowing an override of a `PASS` (nothing to override) or a second
    override of the same check (one auditable decision per check, not a
    place to quietly retry until it looks better)."""
    if check.verdict != VERDICT_BLOCKED:
        raise InvalidOverrideError(f"bias guard check {check.id} is not BLOCKED; nothing to override")
    if not justification or not justification.strip():
        raise InvalidOverrideError("an override requires a real, non-empty justification")

    existing = session.scalar(select(BiasGuardOverride).where(BiasGuardOverride.check_id == check.id))
    if existing is not None:
        raise OverrideAlreadyRecordedError(f"bias guard check {check.id} already has an override")

    override = BiasGuardOverride(
        check_id=check.id,
        justification=justification,
        authorized_by=authorized_by,
        recorded_at=recorded_at,
        override_version=BIAS_GUARD_VERSION,
    )
    session.add(override)
    session.commit()
    session.refresh(override)
    return override


def get_override_for_check(session: Session, check_id: int) -> BiasGuardOverride | None:
    return session.scalar(select(BiasGuardOverride).where(BiasGuardOverride.check_id == check_id))


def is_effectively_passed(check: BiasGuardCheck, override: BiasGuardOverride | None) -> bool:
    """The one function a training/replay/evaluation workflow should call
    to decide "can I actually use this prediction". A `BLOCKED` check
    only counts as usable when a real, separately-recorded override is
    passed in -- never inferred, never assumed."""
    if check.verdict == VERDICT_PASS:
        return True
    return override is not None and override.check_id == check.id


def get_bias_guard_history(session: Session, prediction_id: int) -> tuple[BiasGuardCheck, ...]:
    return tuple(
        session.scalars(
            select(BiasGuardCheck).where(BiasGuardCheck.prediction_id == prediction_id).order_by(BiasGuardCheck.id.asc())
        ).all()
    )
