"""EPIC-M1.58: quantify recommendation-level downside, reward/risk, and
volatility-adjusted risk so users can understand risk before acting --
built entirely on top of M1.47's already-published, already-validated
target/stop-loss, never recomputing or duplicating that validation.

`risk_percentage`/`reward_percentage`/`reward_risk_ratio` are copied
directly from M1.47's `RecommendationPublication` (AC: "published
recommendations expose risk metrics"). This module's own new contribution
is normalizing risk and reward by the underlying `ScanCandidate.atr_percent`
-- "volatility-adjusted risk" (objective) -- and a horizon-consistency
check: a stop distance that is too tight relative to the stock's own
volatility (noise risk) or too wide relative to the recommendation's own
horizon is flagged, not silently accepted (scope: "validate target, stop
loss, upside, and horizon consistency").

Does not provide portfolio allocation advice (non-goal, explicit in scope)
-- this module has no concept of position sizing, capital, or multiple
holdings; it only assesses one recommendation's own risk shape.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import PositionRiskAssessment, Prediction, RecommendationGeneration, RecommendationPublication, ScanCandidate

POSITION_RISK_ASSESSMENT_VERSION = "PRA-001"

# Fixed, documented, versioned policy constants -- not learned or fitted.
# A stop tighter than this many ATRs is noise risk, not a real signal-driven
# stop; a stop wider than this many ATRs per horizon day is inconsistent
# with a recommendation meant to resolve within that horizon.
MIN_ATR_MULTIPLE_STOP = Decimal("0.5")
MAX_ATR_MULTIPLE_PER_HORIZON_DAY = Decimal("2.0")

REASON_STOP_TOO_TIGHT_FOR_VOLATILITY = "STOP_TOO_TIGHT_FOR_VOLATILITY"
REASON_STOP_TOO_WIDE_FOR_HORIZON = "STOP_TOO_WIDE_FOR_HORIZON"


class UnpublishedRecommendationError(ValueError):
    """Raised when attempting to assess risk for a `RecommendationPublication`
    that was itself rejected by M1.47 -- there is no valid target/SL shape to
    assess risk from."""


class PositionRiskAssessmentImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "recommendation_publication_id",
    "risk_percentage",
    "reward_percentage",
    "reward_risk_ratio",
    "atr_percent",
    "risk_in_atr_units",
    "reward_in_atr_units",
    "horizon_days",
    "horizon_consistent",
    "inconsistency_reason",
    "assessed_at",
    "assessment_rule_version",
    "created_at",
)


@event.listens_for(PositionRiskAssessment, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise PositionRiskAssessmentImmutableError(
            f"position risk assessment {target.id} field(s) {changed} cannot be modified after creation"
        )


def _horizon_consistency(risk_in_atr_units: Decimal, horizon_days: int) -> tuple[bool, str | None]:
    if risk_in_atr_units < MIN_ATR_MULTIPLE_STOP:
        return False, REASON_STOP_TOO_TIGHT_FOR_VOLATILITY
    if risk_in_atr_units > MAX_ATR_MULTIPLE_PER_HORIZON_DAY * horizon_days:
        return False, REASON_STOP_TOO_WIDE_FOR_HORIZON
    return True, None


def get_position_risk_assessment(
    session: Session, prediction_id: int, *, assessment_rule_version: str = POSITION_RISK_ASSESSMENT_VERSION
) -> PositionRiskAssessment | None:
    return session.scalar(
        select(PositionRiskAssessment).where(
            PositionRiskAssessment.prediction_id == prediction_id,
            PositionRiskAssessment.assessment_rule_version == assessment_rule_version,
        )
    )


def assess_position_risk(
    session: Session,
    prediction: Prediction,
    publication: RecommendationPublication,
    *,
    assessed_at: datetime,
    assessment_rule_version: str = POSITION_RISK_ASSESSMENT_VERSION,
) -> PositionRiskAssessment:
    """Deterministic and auditable (AC): a pure function of `publication`'s
    own already-validated fields plus the underlying `ScanCandidate.
    atr_percent`. Idempotent by `(prediction_id, assessment_rule_version)`
    -- historical recommendations retain their original risk snapshot (AC)
    even if re-assessed later. Raises `UnpublishedRecommendationError` if
    `publication.published` is `False` -- there is no valid target/SL to
    assess risk from (AC: "invalid target/SL combinations are rejected")."""
    existing = get_position_risk_assessment(session, prediction.id, assessment_rule_version=assessment_rule_version)
    if existing is not None:
        return existing

    if not publication.published:
        raise UnpublishedRecommendationError(
            f"prediction {prediction.id}'s publication was rejected ({publication.rejection_reason}); "
            "cannot assess risk for an unpublished recommendation"
        )

    scan_candidate = session.execute(
        select(ScanCandidate)
        .join(RecommendationGeneration, RecommendationGeneration.scan_candidate_id == ScanCandidate.id)
        .where(RecommendationGeneration.prediction_id == prediction.id)
    ).scalars().first()
    atr_percent = scan_candidate.atr_percent

    risk_in_atr_units = publication.downside_percentage / atr_percent
    reward_in_atr_units = publication.upside_percentage / atr_percent
    horizon_consistent, inconsistency_reason = _horizon_consistency(risk_in_atr_units, prediction.horizon_days)

    assessment = PositionRiskAssessment(
        prediction_id=prediction.id,
        recommendation_publication_id=publication.id,
        risk_percentage=publication.downside_percentage,
        reward_percentage=publication.upside_percentage,
        reward_risk_ratio=publication.reward_risk_ratio,
        atr_percent=atr_percent,
        risk_in_atr_units=risk_in_atr_units,
        reward_in_atr_units=reward_in_atr_units,
        horizon_days=prediction.horizon_days,
        horizon_consistent=horizon_consistent,
        inconsistency_reason=inconsistency_reason,
        assessed_at=assessed_at,
        assessment_rule_version=assessment_rule_version,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment
