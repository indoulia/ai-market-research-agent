"""EPIC-M1.54: ensure recommendation evidence (M1.48) remains fresh enough
for the recommendation's own selected horizon, and record whenever a
material change requires revalidation.

Generalizes M1.35's flat per-data-type freshness policy to be horizon-aware:
a longer-horizon recommendation can tolerate more staleness than a short one
before its evidence needs revalidating. The base per-data-type threshold
(`FRESHNESS_POLICY`) is reused unchanged from M1.35; this module only scales
it by horizon.

Every check -- fresh or not -- is recorded as an immutable, append-only
`EvidenceRevalidationCheck` row, the same "record every attempt" precedent
M1.35's own `DataFetchAttempt` already established. This module never
writes to `RecommendationEvidenceItem` (M1.48's own snapshot table) at all,
so "revalidation never silently mutates the original snapshot" (AC) holds
structurally.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .evidence_snapshot import (
    EVIDENCE_CATEGORY_EVENT,
    EVIDENCE_CATEGORY_FUNDAMENTAL,
    EVIDENCE_CATEGORY_MARKET_SECTOR,
    EVIDENCE_CATEGORY_NEWS,
    EVIDENCE_CATEGORY_TECHNICAL_VOLUME,
    STATUS_UNAVAILABLE,
)
from .models import EvidenceRevalidationCheck, Prediction, RecommendationEvidenceItem
from .refresh_policy import DATA_TYPE_FUNDAMENTAL, DATA_TYPE_MARKET, DATA_TYPE_NEWS_EVENT, FRESHNESS_POLICY, check_market_data_freshness

EVIDENCE_REVALIDATION_VERSION = "ERV-001"

# A longer horizon can tolerate more staleness before revalidation is
# required. Fixed, documented, versioned scaling -- not learned or fitted.
# Never makes a threshold *smaller* than M1.35's own base policy.
HORIZON_FRESHNESS_FRACTION = Decimal("0.5")

_CATEGORY_TO_DATA_TYPE = {
    EVIDENCE_CATEGORY_FUNDAMENTAL: DATA_TYPE_FUNDAMENTAL,
    EVIDENCE_CATEGORY_NEWS: DATA_TYPE_NEWS_EVENT,
    EVIDENCE_CATEGORY_EVENT: DATA_TYPE_NEWS_EVENT,
    EVIDENCE_CATEGORY_MARKET_SECTOR: DATA_TYPE_MARKET,
    EVIDENCE_CATEGORY_TECHNICAL_VOLUME: DATA_TYPE_MARKET,
}

REASON_STALE = "STALE"
REASON_MISSING = "MISSING"
REASON_CHANGED = "CHANGED"
REASON_CONFLICTING = "CONFLICTING"  # reserved: no evidence category in this repo has two independent sources yet


class EvidenceRevalidationImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "recommendation_evidence_item_id",
    "evidence_category",
    "horizon_days",
    "freshness_threshold_seconds",
    "revalidation_required",
    "reason",
    "original_value",
    "current_value",
    "checked_at",
    "revalidation_rule_version",
    "created_at",
)


@event.listens_for(EvidenceRevalidationCheck, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise EvidenceRevalidationImmutableError(
            f"evidence revalidation check {target.id} field(s) {changed} cannot be modified after creation"
        )


def horizon_aware_threshold(evidence_category: str, horizon_days: int) -> timedelta:
    """Each evidence category's M1.35 base threshold (AC: "each evidence
    category has an explicit freshness policy"), scaled by horizon (AC:
    "freshness is evaluated relative to recommendation horizon") -- never
    smaller than the base."""
    data_type = _CATEGORY_TO_DATA_TYPE[evidence_category]
    base = FRESHNESS_POLICY[data_type]
    scaled = timedelta(days=horizon_days) * float(HORIZON_FRESHNESS_FRACTION)
    return max(base, scaled)


def revalidate_evidence(
    session: Session,
    prediction: Prediction,
    evidence_item: RecommendationEvidenceItem,
    *,
    checked_at: datetime,
) -> EvidenceRevalidationCheck:
    """Re-checks one M1.48 evidence item's freshness against the
    horizon-aware threshold as of `checked_at`, and -- for `TECHNICAL_VOLUME`
    specifically, where a cheap, real re-check is possible -- whether
    materially new market data has arrived since the snapshot was captured
    (AC: "material changes trigger revalidation"). Always records a new,
    immutable check row, whether or not revalidation is required."""
    threshold = horizon_aware_threshold(evidence_item.evidence_category, prediction.horizon_days)

    if evidence_item.status == STATUS_UNAVAILABLE:
        reason = REASON_MISSING
        revalidation_required = True
        original_value = None
        current_value = None
    else:
        original_value = str(evidence_item.evidence_timestamp) if evidence_item.evidence_timestamp else None
        current_value = original_value
        reason = None
        revalidation_required = False

        if evidence_item.evidence_timestamp is not None:
            # sqlite drops tzinfo on round-trip, unlike Postgres; every
            # timestamp here is UTC-based by convention.
            staleness = checked_at.replace(tzinfo=None) - evidence_item.evidence_timestamp.replace(tzinfo=None)
            if staleness > threshold:
                reason = REASON_STALE
                revalidation_required = True

        if evidence_item.evidence_category == EVIDENCE_CATEGORY_TECHNICAL_VOLUME:
            fresh_check = check_market_data_freshness(session, prediction.stock_id, checked_at)
            current_value = str(fresh_check.source_timestamp) if fresh_check.source_timestamp else None
            if current_value != original_value:
                reason = REASON_CHANGED
                revalidation_required = True

    check = EvidenceRevalidationCheck(
        prediction_id=prediction.id,
        recommendation_evidence_item_id=evidence_item.id,
        evidence_category=evidence_item.evidence_category,
        horizon_days=prediction.horizon_days,
        freshness_threshold_seconds=int(threshold.total_seconds()),
        revalidation_required=revalidation_required,
        reason=reason,
        original_value=original_value,
        current_value=current_value,
        checked_at=checked_at,
        revalidation_rule_version=EVIDENCE_REVALIDATION_VERSION,
    )
    session.add(check)
    session.commit()
    session.refresh(check)
    return check


def get_revalidation_history(session: Session, prediction_id: int) -> tuple[EvidenceRevalidationCheck, ...]:
    return tuple(
        session.scalars(
            select(EvidenceRevalidationCheck)
            .where(EvidenceRevalidationCheck.prediction_id == prediction_id)
            .order_by(EvidenceRevalidationCheck.id.asc())
        ).all()
    )
