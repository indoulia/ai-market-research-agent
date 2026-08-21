"""EPIC-M1.65: resolve or explicitly surface conflicting evidence for one
recommendation -- market, news, event, and fundamental -- producing an
explicit `RESOLVED`/`UNRESOLVED`/`INSUFFICIENT_EVIDENCE` state.

Given this repo's real evidence sources (M1.48: technical/volume and
market/sector are real where available; news is M1.17's discovery
rationale; fundamental and event have no real ingestion pipeline at all), a
literal fact-vs-fact contradiction between two evidence categories cannot
happen -- there is no second, independent source for the same fact. This
module instead detects the two genuine conflict shapes this platform's data
actually supports:

1. **Untrusted-source conflict**: an evidence item that appears `AVAILABLE`
   or `STALE` (M1.48) whose underlying category M1.64 has separately
   assessed as untrusted (`EvidenceQualityStatus.trusted is False`) -- the
   evidence *looks* present, but the reliability layer says not to trust
   it. This is the "compare source reliability and freshness" scope item.
2. **Revalidation conflict**: M1.62's most recent revalidation outcome for
   this prediction is `WITHDRAWN` or `UPDATED` -- a materially different
   signal than the "still fully valid" assumption the still-open
   recommendation currently rests on.

Composes M1.48 (`get_evidence_snapshot`), M1.64
(`compute_data_source_reliability_report`), and M1.62
(`get_revalidation_history`) directly; modifies none of them. Never writes
to `Prediction`, `RecommendationEvidenceItem`, or any revalidation/alert
table -- "historical evidence remains immutable" (AC) holds structurally.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .data_source_reliability import DataSourceReliabilityReport
from .evidence_snapshot import STATUS_UNAVAILABLE, get_evidence_snapshot
from .models import EvidenceConflictResolution, Prediction
from .recommendation_revalidation import OUTCOME_UPDATED, OUTCOME_WITHDRAWN, get_revalidation_history

RESOLUTION_RULE_VERSION = "ECR-001"

STATE_RESOLVED = "RESOLVED"
STATE_UNRESOLVED = "UNRESOLVED"
STATE_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

REASON_UNTRUSTED_SOURCE = "UNTRUSTED_SOURCE"
REASON_REVALIDATION_CONFLICT = "REVALIDATION_CONFLICT"

# Each unresolved conflict reduces the confidence ceiling by this much,
# capped at zero. Fixed, documented, versioned -- not learned or fitted.
CONFIDENCE_CONFLICT_PENALTY = Decimal("0.15")

# Any unresolved conflict is treated as material enough to flag for
# blocking -- a conservative default, not a fitted threshold.
MATERIAL_CONFLICT_THRESHOLD = 1


def resolve_evidence_conflicts(
    session: Session,
    prediction: Prediction,
    *,
    reliability_report: DataSourceReliabilityReport,
    resolved_at: datetime,
) -> EvidenceConflictResolution:
    """Deterministic (AC: "conflict resolution is deterministic and
    explainable") given `reliability_report` and the current revalidation
    history. Idempotent by `(prediction_id, resolved_at)` -- a later
    `resolved_at` legitimately re-resolves against fresh evidence."""
    existing = session.scalar(
        select(EvidenceConflictResolution).where(
            EvidenceConflictResolution.prediction_id == prediction.id,
            EvidenceConflictResolution.resolved_at == resolved_at,
        )
    )
    if existing is not None:
        return existing

    evidence_items = get_evidence_snapshot(session, prediction.id)
    categories_considered = [item.evidence_category for item in evidence_items]

    conflicts = []
    for item in evidence_items:
        status = next((s for s in reliability_report.quality_statuses if s.key == item.evidence_category), None)
        if item.status != STATUS_UNAVAILABLE and status is not None and not status.trusted:
            conflicts.append({"category": item.evidence_category, "reason": REASON_UNTRUSTED_SOURCE, "detail": status.reason})

    revalidations = get_revalidation_history(session, prediction.id)
    if revalidations:
        latest = revalidations[-1]
        if latest.outcome in (OUTCOME_WITHDRAWN, OUTCOME_UPDATED):
            conflicts.append({"category": None, "reason": REASON_REVALIDATION_CONFLICT, "detail": latest.reason})

    conflict_count = len(conflicts)

    if not evidence_items and not revalidations:
        state = STATE_INSUFFICIENT_EVIDENCE
        confidence_adjustment_ceiling = None
        blocks_qualification = False
    elif conflict_count == 0:
        state = STATE_RESOLVED
        confidence_adjustment_ceiling = prediction.confidence
        blocks_qualification = False
    else:
        state = STATE_UNRESOLVED
        confidence_adjustment_ceiling = max(
            Decimal("0"), prediction.confidence - CONFIDENCE_CONFLICT_PENALTY * conflict_count
        )
        blocks_qualification = conflict_count >= MATERIAL_CONFLICT_THRESHOLD

    resolution = EvidenceConflictResolution(
        prediction_id=prediction.id,
        state=state,
        conflict_count=conflict_count,
        conflicts=conflicts,
        evidence_categories_considered=categories_considered,
        confidence_adjustment_ceiling=confidence_adjustment_ceiling,
        blocks_qualification=blocks_qualification,
        resolved_at=resolved_at,
        resolution_rule_version=RESOLUTION_RULE_VERSION,
    )
    session.add(resolution)
    session.commit()
    session.refresh(resolution)
    return resolution


def get_conflict_resolution_history(session: Session, prediction_id: int) -> tuple[EvidenceConflictResolution, ...]:
    return tuple(
        session.scalars(
            select(EvidenceConflictResolution)
            .where(EvidenceConflictResolution.prediction_id == prediction_id)
            .order_by(EvidenceConflictResolution.id.asc())
        ).all()
    )
