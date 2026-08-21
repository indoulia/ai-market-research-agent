"""EPIC-M1.74: a single, per-recommendation evidence-completeness and
point-in-time data-quality gate over M1.48's evidence snapshot.

This is deliberately a different lens than M1.65's `evidence_conflict_
resolution`, not a duplicate: M1.65 asks "does this evidence conflict
with something else" (an untrusted *global* source per M1.64's aggregate
reliability report, or a revalidation outcome); this module asks "is this
one recommendation's own evidence snapshot, taken by itself, complete
and safe" -- a strictly local, per-snapshot question that needs no
reliability report and no revalidation history at all. Both modules are
read-only "propose, never apply" evidence layers over the exact same
M1.48 snapshot, mirroring the platform's established `confidence_
adjustment_ceiling`/`blocks_qualification`-style split (neither this
module nor M1.65 is itself wired into `target_stop_loss`'s publish gate
today -- both only make the capability available, per this EPIC's own
AC: evidence quality *can* lower confidence or block publication "when
policy requires").

"Detect ... future-dated evidence" (scope) is a defense-in-depth check:
every M1.48 category builder already only ever selects evidence with an
`evidence_timestamp <= prediction.as_of_timestamp` by construction, so
this should never fire in practice -- but this module makes that
invariant an explicit, tested, auditable gate rather than an implicit
assumption buried in five different builder functions.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .evidence_snapshot import ALL_EVIDENCE_CATEGORIES, STATUS_AVAILABLE, STATUS_STALE, STATUS_UNAVAILABLE, get_evidence_snapshot
from .models import EvidenceQualityDecision, Prediction

EVIDENCE_QUALITY_GATE_VERSION = "EQG-001"

STATE_SUFFICIENT = "SUFFICIENT"
STATE_INSUFFICIENT = "INSUFFICIENT"
STATE_LEAKAGE_DETECTED = "LEAKAGE_DETECTED"

REASON_NO_EVIDENCE_CAPTURED = "NO_EVIDENCE_CAPTURED"
REASON_TOO_FEW_AVAILABLE_CATEGORIES = "TOO_FEW_AVAILABLE_CATEGORIES"
REASON_FUTURE_DATED_EVIDENCE = "FUTURE_DATED_EVIDENCE"

# Fixed, documented, versioned policy: at least this many of the five
# M1.48 evidence categories must be AVAILABLE (not stale, not
# unavailable) for a recommendation's evidence to be considered complete.
# TECHNICAL_VOLUME is always real for a qualified recommendation and
# MARKET_SECTOR is real whenever `Stock.sector` is set (nearly always),
# so this floor is achievable today without depending on the honestly
# partial FUNDAMENTAL/NEWS/EVENT categories.
MIN_AVAILABLE_CATEGORIES = 2


class EvidenceQualityDecisionImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "state",
    "available_category_count",
    "stale_category_count",
    "unavailable_category_count",
    "categories_considered",
    "leaked_categories",
    "reasons",
    "confidence_adjustment_ceiling",
    "blocks_publication",
    "evaluated_at",
    "gate_rule_version",
    "created_at",
)


@event.listens_for(EvidenceQualityDecision, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise EvidenceQualityDecisionImmutableError(
            f"evidence quality decision {target.id} field(s) {changed} cannot be modified after creation"
        )


def _leaked_categories(items, as_of_timestamp: datetime) -> list[str]:
    naive_as_of = as_of_timestamp.replace(tzinfo=None)
    return [
        item.evidence_category
        for item in items
        if item.evidence_timestamp is not None and item.evidence_timestamp.replace(tzinfo=None) > naive_as_of
    ]


def evaluate_evidence_quality(
    session: Session, prediction: Prediction, *, evaluated_at: datetime
) -> EvidenceQualityDecision:
    """Deterministic given `prediction`'s already-captured M1.48 snapshot
    (AC: "quality decisions are reproducible and auditable") -- never
    invents evidence a category doesn't have (scope: "without inventing
    missing data") and never writes to `Prediction`/`RecommendationEvidenceItem`
    itself. Idempotent by `(prediction_id, evaluated_at)`."""
    existing = session.scalar(
        select(EvidenceQualityDecision).where(
            EvidenceQualityDecision.prediction_id == prediction.id,
            EvidenceQualityDecision.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    items = get_evidence_snapshot(session, prediction.id)
    categories_considered = [item.evidence_category for item in items]
    available = sum(1 for item in items if item.status == STATUS_AVAILABLE)
    stale = sum(1 for item in items if item.status == STATUS_STALE)
    unavailable = sum(1 for item in items if item.status == STATUS_UNAVAILABLE)
    leaked = _leaked_categories(items, prediction.as_of_timestamp)

    reasons = []
    if not items:
        reasons.append(REASON_NO_EVIDENCE_CAPTURED)
    elif available < MIN_AVAILABLE_CATEGORIES:
        reasons.append(REASON_TOO_FEW_AVAILABLE_CATEGORIES)
    if leaked:
        reasons.append(REASON_FUTURE_DATED_EVIDENCE)

    if leaked:
        state = STATE_LEAKAGE_DETECTED
        confidence_adjustment_ceiling = Decimal("0")
    elif not items or available < MIN_AVAILABLE_CATEGORIES:
        state = STATE_INSUFFICIENT
        confidence_adjustment_ceiling = (
            Decimal("0")
            if not items
            else prediction.confidence * Decimal(available) / Decimal(len(ALL_EVIDENCE_CATEGORIES))
        )
    else:
        state = STATE_SUFFICIENT
        confidence_adjustment_ceiling = prediction.confidence

    decision = EvidenceQualityDecision(
        prediction_id=prediction.id,
        state=state,
        available_category_count=available,
        stale_category_count=stale,
        unavailable_category_count=unavailable,
        categories_considered=categories_considered,
        leaked_categories=leaked,
        reasons=reasons,
        confidence_adjustment_ceiling=confidence_adjustment_ceiling,
        blocks_publication=(state != STATE_SUFFICIENT),
        evaluated_at=evaluated_at,
        gate_rule_version=EVIDENCE_QUALITY_GATE_VERSION,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def get_quality_decision_history(session: Session, prediction_id: int) -> tuple[EvidenceQualityDecision, ...]:
    return tuple(
        session.scalars(
            select(EvidenceQualityDecision)
            .where(EvidenceQualityDecision.prediction_id == prediction_id)
            .order_by(EvidenceQualityDecision.id.asc())
        ).all()
    )
