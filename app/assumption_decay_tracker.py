"""EPIC-M1.112: automatically detect when the assumptions behind an
active prediction have materially decayed with the passage of time,
and recommend invalidation without ever exposing a negative/cautious
recommendation.

**Track assumptions supporting each prediction**: every M1.48 evidence
category that was `STATUS_AVAILABLE` at capture time -- `FUNDAMENTAL`,
`NEWS`, `EVENT`, `MARKET_SECTOR`, `TECHNICAL_VOLUME` -- is one tracked
assumption. `MARKET_SECTOR` is excluded from decay checking: it reflects
`Stock.sector`, a largely static classification with no real "freshness
window" concept in this platform (M1.35's `FRESHNESS_POLICY` has no
entry for it), so it is honestly reported as always non-decaying rather
than assigned an invented threshold.

**Define assumption freshness/decay rules**: reuses M1.35's own
`FRESHNESS_POLICY` thresholds unchanged, applied against the *original*
`evidence_timestamp` M1.48 froze at capture time but compared against
`evaluated_at` (now) rather than the prediction's own `as_of_timestamp`
(then) -- a genuinely new check M1.74's own evidence-quality gate never
performs, since that gate only ever asks "was this evidence fresh
*when captured*," never "is it still fresh *now*."

**Detect material contradiction or thesis break / trigger revalidation
or invalidation**: `decay_ratio` is the fraction of tracked (non-
`MARKET_SECTOR`) categories that have crossed their freshness window
since capture; `MATERIAL_DECAY` (a majority decayed) recommends
invalidation. This is a propose-only signal -- `invalidation_recommended`
has no write path to `Prediction` or any recommendation-facing table;
an actual revalidation/revision remains M1.62/M1.55/M1.105's job.

**Preserve original and revised prediction history / feed invalidation
outcomes into learning**: this module never mutates `RecommendationEvidenceItem`
or any revision table -- every assessment is a new, immutable,
idempotent-by-`(prediction_id, evaluated_at)` row.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .evidence_snapshot import (
    EVIDENCE_CATEGORY_EVENT,
    EVIDENCE_CATEGORY_FUNDAMENTAL,
    EVIDENCE_CATEGORY_MARKET_SECTOR,
    EVIDENCE_CATEGORY_NEWS,
    EVIDENCE_CATEGORY_TECHNICAL_VOLUME,
    STATUS_AVAILABLE,
    get_evidence_snapshot,
)
from .models import AssumptionDecayAssessment, Prediction
from .refresh_policy import DATA_TYPE_FUNDAMENTAL, DATA_TYPE_MARKET, DATA_TYPE_NEWS_EVENT, FRESHNESS_POLICY

DECAY_RULE_VERSION = "ADT-001"

VERDICT_NO_DECAY = "NO_DECAY"
VERDICT_PARTIAL_DECAY = "PARTIAL_DECAY"
VERDICT_MATERIAL_DECAY = "MATERIAL_DECAY"

# Fixed, documented, versioned policy constant: a majority of tracked
# assumptions decaying is material enough to recommend invalidation --
# not learned or fitted.
MATERIAL_DECAY_RATIO_THRESHOLD = Decimal("0.5")

# M1.35's freshness policy has no real notion of "sector freshness" --
# a static classification, not a fetched-and-aging data point.
_CATEGORY_TO_DATA_TYPE = {
    EVIDENCE_CATEGORY_TECHNICAL_VOLUME: DATA_TYPE_MARKET,
    EVIDENCE_CATEGORY_FUNDAMENTAL: DATA_TYPE_FUNDAMENTAL,
    EVIDENCE_CATEGORY_NEWS: DATA_TYPE_NEWS_EVENT,
    EVIDENCE_CATEGORY_EVENT: DATA_TYPE_NEWS_EVENT,
}
_UNTRACKED_CATEGORIES = (EVIDENCE_CATEGORY_MARKET_SECTOR,)


def assess_assumption_decay(session: Session, prediction: Prediction, *, evaluated_at: datetime) -> AssumptionDecayAssessment:
    """Idempotent by `(prediction_id, evaluated_at)`."""
    existing = session.scalar(
        select(AssumptionDecayAssessment).where(
            AssumptionDecayAssessment.prediction_id == prediction.id, AssumptionDecayAssessment.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    items = get_evidence_snapshot(session, prediction.id)
    naive_evaluated_at = evaluated_at.replace(tzinfo=None)

    tracked_categories: list[str] = []
    decayed_categories: list[str] = []
    for item in items:
        if item.status != STATUS_AVAILABLE or item.evidence_category in _UNTRACKED_CATEGORIES:
            continue
        data_type = _CATEGORY_TO_DATA_TYPE.get(item.evidence_category)
        if data_type is None or item.evidence_timestamp is None:
            continue
        tracked_categories.append(item.evidence_category)
        age = naive_evaluated_at - item.evidence_timestamp.replace(tzinfo=None)
        if age > FRESHNESS_POLICY[data_type]:
            decayed_categories.append(item.evidence_category)

    tracked_count = len(tracked_categories)
    if tracked_count == 0:
        decay_ratio = None
        verdict = VERDICT_NO_DECAY
    else:
        decay_ratio = Decimal(len(decayed_categories)) / Decimal(tracked_count)
        if decay_ratio == 0:
            verdict = VERDICT_NO_DECAY
        elif decay_ratio >= MATERIAL_DECAY_RATIO_THRESHOLD:
            verdict = VERDICT_MATERIAL_DECAY
        else:
            verdict = VERDICT_PARTIAL_DECAY

    assessment = AssumptionDecayAssessment(
        prediction_id=prediction.id, tracked_categories=sorted(tracked_categories), decayed_categories=sorted(decayed_categories),
        decay_ratio=decay_ratio, verdict=verdict, invalidation_recommended=(verdict == VERDICT_MATERIAL_DECAY),
        evaluated_at=evaluated_at, decay_rule_version=DECAY_RULE_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_assumption_decay_history(session: Session, prediction_id: int) -> tuple[AssumptionDecayAssessment, ...]:
    return tuple(
        session.scalars(
            select(AssumptionDecayAssessment).where(AssumptionDecayAssessment.prediction_id == prediction_id).order_by(AssumptionDecayAssessment.id.asc())
        ).all()
    )
