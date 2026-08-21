"""EPIC-M1.60: provide optional, risk-aware allocation guidance based on
user-declared limits, without ever executing a trade.

`UserAllocationLimit` is versioned and append-only -- the same "a user can
change limits without mutating history" pattern M1.46 already established
for `UserPreference`. Guidance itself (`AllocationGuidance`) is a pure,
read-only computation, never persisted: it is explicitly advisory, not a
financial record, and this module has no write path for it at all (AC: "no
automatic order execution exists").

Composes rather than duplicates: M1.58's `PositionRiskAssessment`
(volatility-adjusted risk) is the sole risk input -- if none exists, or the
one that does exist is itself horizon-inconsistent, guidance is refused
outright (AC: "missing risk information prevents unsafe guidance") rather
than falling back to a fabricated risk estimate. M1.59's
`assess_portfolio_conflict` is the sole portfolio/concentration input
(scope: "respect portfolio and concentration constraints").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Prediction, PositionRiskAssessment, UserAllocationLimit
from .portfolio_awareness import assess_portfolio_conflict

ALLOCATION_LIMIT_VERSION = "AGL-001"
ALLOCATION_GUIDANCE_VERSION = "AGD-001"

DEFAULT_MAX_POSITION_PERCENTAGE = Decimal("0.10")
DEFAULT_MAX_SECTOR_PERCENTAGE = Decimal("0.30")

# A fixed, documented, versioned base-allocation formula -- not learned or
# fitted. Scales up with confidence, down with volatility-adjusted risk.
MAX_BASE_ALLOCATION_PERCENTAGE = Decimal("0.10")

# A sector already at the concentration threshold halves the suggested
# allocation rather than blocking it outright -- a soft constraint, distinct
# from the hard block for a stock the user already has exposure to.
SECTOR_CONCENTRATION_REDUCTION_FACTOR = Decimal("0.5")

GUIDANCE_STATUS_GUIDED = "GUIDED"
GUIDANCE_STATUS_CONSTRAINED = "CONSTRAINED"
GUIDANCE_STATUS_BLOCKED = "BLOCKED"
GUIDANCE_STATUS_INSUFFICIENT_RISK_INFORMATION = "INSUFFICIENT_RISK_INFORMATION"

REASON_NO_RISK_ASSESSMENT = "NO_RISK_ASSESSMENT"
REASON_HORIZON_INCONSISTENT_RISK = "HORIZON_INCONSISTENT_RISK"
REASON_CAPPED_BY_USER_LIMIT = "CAPPED_BY_USER_LIMIT"
REASON_SECTOR_CONCENTRATION = "SECTOR_CONCENTRATION"
REASON_ALREADY_EXPOSED = "ALREADY_EXPOSED"


class InvalidAllocationLimitError(ValueError):
    pass


@dataclass(frozen=True)
class AllocationGuidance:
    version: str
    user_id: str
    prediction_id: int
    suggested_allocation_percentage: Decimal | None
    guidance_status: str
    reasons: tuple[str, ...]


def set_allocation_limit(
    session: Session,
    *,
    user_id: str,
    effective_at: datetime,
    max_position_percentage: Decimal = DEFAULT_MAX_POSITION_PERCENTAGE,
    max_sector_percentage: Decimal = DEFAULT_MAX_SECTOR_PERCENTAGE,
) -> UserAllocationLimit:
    """Always inserts a new version -- never mutates a prior one (the same
    pattern M1.46 established for `UserPreference`)."""
    if not (Decimal("0") < max_position_percentage <= Decimal("1")):
        raise InvalidAllocationLimitError(f"max_position_percentage must be within (0, 1], got {max_position_percentage}")
    if not (Decimal("0") < max_sector_percentage <= Decimal("1")):
        raise InvalidAllocationLimitError(f"max_sector_percentage must be within (0, 1], got {max_sector_percentage}")

    limit = UserAllocationLimit(
        user_id=user_id,
        max_position_percentage=max_position_percentage,
        max_sector_percentage=max_sector_percentage,
        effective_at=effective_at,
        limit_rule_version=ALLOCATION_LIMIT_VERSION,
    )
    session.add(limit)
    session.commit()
    session.refresh(limit)
    return limit


def get_current_allocation_limit(session: Session, user_id: str, *, effective_at: datetime) -> UserAllocationLimit:
    """Lazily creates and returns a real, persisted default limit if this
    user has never set one -- idempotent, mirroring M1.46's
    `get_current_preference`."""
    existing = session.scalar(
        select(UserAllocationLimit).where(UserAllocationLimit.user_id == user_id).order_by(UserAllocationLimit.id.desc())
    )
    if existing is not None:
        return existing
    return set_allocation_limit(session, user_id=user_id, effective_at=effective_at)


def generate_allocation_guidance(
    session: Session,
    *,
    user_id: str,
    prediction: Prediction,
    risk_assessment: PositionRiskAssessment | None,
    effective_at: datetime,
) -> AllocationGuidance:
    """Deterministic, read-only, advisory guidance (AC: "guidance is
    deterministic and capped by user limits") -- never writes anything.
    Refuses to guide at all without a horizon-consistent risk assessment
    (AC: "missing risk information prevents unsafe guidance")."""
    if risk_assessment is None:
        return AllocationGuidance(
            version=ALLOCATION_GUIDANCE_VERSION, user_id=user_id, prediction_id=prediction.id,
            suggested_allocation_percentage=None, guidance_status=GUIDANCE_STATUS_INSUFFICIENT_RISK_INFORMATION,
            reasons=(REASON_NO_RISK_ASSESSMENT,),
        )
    if not risk_assessment.horizon_consistent:
        return AllocationGuidance(
            version=ALLOCATION_GUIDANCE_VERSION, user_id=user_id, prediction_id=prediction.id,
            suggested_allocation_percentage=None, guidance_status=GUIDANCE_STATUS_INSUFFICIENT_RISK_INFORMATION,
            reasons=(REASON_HORIZON_INCONSISTENT_RISK,),
        )

    limit = get_current_allocation_limit(session, user_id, effective_at=effective_at)
    base_allocation = MAX_BASE_ALLOCATION_PERCENTAGE * prediction.confidence / (Decimal("1") + risk_assessment.risk_in_atr_units)

    reasons = []
    capped_allocation = base_allocation
    if capped_allocation > limit.max_position_percentage:
        capped_allocation = limit.max_position_percentage
        reasons.append(REASON_CAPPED_BY_USER_LIMIT)

    conflict = assess_portfolio_conflict(session, user_id=user_id, candidate_stock_id=prediction.stock_id)

    if conflict.already_held or conflict.already_active_recommendation:
        return AllocationGuidance(
            version=ALLOCATION_GUIDANCE_VERSION, user_id=user_id, prediction_id=prediction.id,
            suggested_allocation_percentage=Decimal("0"), guidance_status=GUIDANCE_STATUS_BLOCKED,
            reasons=(REASON_ALREADY_EXPOSED,),
        )

    if conflict.sector_concentration_warning:
        capped_allocation = capped_allocation * SECTOR_CONCENTRATION_REDUCTION_FACTOR
        reasons.append(REASON_SECTOR_CONCENTRATION)

    status = GUIDANCE_STATUS_CONSTRAINED if reasons else GUIDANCE_STATUS_GUIDED
    return AllocationGuidance(
        version=ALLOCATION_GUIDANCE_VERSION, user_id=user_id, prediction_id=prediction.id,
        suggested_allocation_percentage=capped_allocation, guidance_status=status, reasons=tuple(reasons),
    )
