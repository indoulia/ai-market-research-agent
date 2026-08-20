"""EPIC-M1.46: let each user define investment preferences that control
which of M1.14's already-selected recommendations are surfaced to them,
without changing M1.9's scoring, M1.10's horizon selection, M1.13's
generation, or M1.14's system-wide daily selection in any way -- "the
underlying historical truth or recommendation contract" (objective).

Two append-only tables:
- `UserPreference`: versioned per user, the same "the log is the pointer"
  pattern M1.31/M1.44 already established -- the most recent row for a
  `user_id` is that user's current effective preference, so changing a
  preference is always a new insert, never a mutation of a prior version
  (AC: "a user can change horizon and supported preferences"; "preference
  changes do not mutate historical recommendations").
- `RecommendationPreferenceSnapshot`: records, immutably and idempotently
  per `(user_id, recommendation_generation_id)`, exactly which preference
  version was in effect and whether that recommendation matched it (AC:
  "recommendation generation records the effective preference snapshot").

Horizon and market-cap-bucket preferences reuse this platform's own existing
vocabulary (`app.recommendations.VALID_HORIZON_DAYS`, `app.consensus.
MIN_CONFIDENCE`, `app.discovery_segmentation`'s market-cap bucket set)
rather than inventing parallel ones. Sector preference has no fixed
vocabulary to validate against (`Stock.sector` is free text) and is always
soft -- it never excludes a recommendation, only flags a preference match.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .consensus import MIN_CONFIDENCE
from .discovery_segmentation import BUCKET_UNCLASSIFIED, MARKET_CAP_BUCKET_THRESHOLDS, classify_market_cap_bucket
from .models import Prediction, RecommendationGeneration, RecommendationPreferenceSnapshot, ScanCandidate, Stock, UserPreference
from .recommendation_selection import select_recommendations_for_scan
from .recommendations import VALID_HORIZON_DAYS

PREFERENCE_RULE_VERSION = "UIP-001"

HORIZON_BAND_SHORT = "SHORT"
HORIZON_BAND_MEDIUM = "MEDIUM"
HORIZON_BAND_LONG = "LONG"
HORIZON_BAND_CUSTOM = "CUSTOM"
VALID_HORIZON_BANDS = (HORIZON_BAND_SHORT, HORIZON_BAND_MEDIUM, HORIZON_BAND_LONG, HORIZON_BAND_CUSTOM)
DEFAULT_HORIZON_BAND = HORIZON_BAND_SHORT

# Fixed, documented, versioned day ranges -- not learned or fitted. SHORT
# spans this platform's entire currently-populated horizon range
# (`VALID_HORIZON_DAYS` = 1-7); MEDIUM/LONG are defined for forward
# compatibility even though M1.10 has never produced a prediction in those
# ranges yet -- a user selecting them today honestly sees zero matches
# rather than a fabricated one.
HORIZON_BAND_DAY_RANGES = {
    HORIZON_BAND_SHORT: (1, 7),
    HORIZON_BAND_MEDIUM: (8, 30),
    HORIZON_BAND_LONG: (31, None),
}

RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"
VALID_RISK_PREFERENCES = (RISK_LOW, RISK_MEDIUM, RISK_HIGH)
DEFAULT_RISK_PREFERENCE = RISK_MEDIUM

DEFAULT_MIN_CONFIDENCE_THRESHOLD = MIN_CONFIDENCE

VALID_MARKET_CAP_BUCKETS = frozenset({bucket for _, bucket in MARKET_CAP_BUCKET_THRESHOLDS} | {BUCKET_UNCLASSIFIED})

REASON_NOT_IN_HORIZON_BAND = "NOT_IN_HORIZON_BAND"
REASON_BELOW_MIN_CONFIDENCE = "BELOW_MIN_CONFIDENCE"


class InvalidPreferenceError(ValueError):
    pass


class UserPreferenceImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "user_id",
    "horizon_band",
    "custom_horizon_days",
    "risk_preference",
    "min_confidence_threshold",
    "preferred_sectors",
    "preferred_market_cap_buckets",
    "effective_at",
    "preference_rule_version",
    "created_at",
)


@event.listens_for(UserPreference, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise UserPreferenceImmutableError(
            f"user preference {target.id} field(s) {changed} cannot be modified after creation -- set a new preference instead"
        )


def _validate_preference(
    *,
    horizon_band: str,
    custom_horizon_days: int | None,
    risk_preference: str,
    min_confidence_threshold: Decimal,
    preferred_market_cap_buckets: list | None,
) -> None:
    if horizon_band not in VALID_HORIZON_BANDS:
        raise InvalidPreferenceError(f"horizon_band must be one of {VALID_HORIZON_BANDS}, got {horizon_band!r}")
    if horizon_band == HORIZON_BAND_CUSTOM:
        if custom_horizon_days is None:
            raise InvalidPreferenceError("custom_horizon_days is required when horizon_band is CUSTOM")
        if custom_horizon_days not in VALID_HORIZON_DAYS:
            raise InvalidPreferenceError(f"custom_horizon_days must be one of {VALID_HORIZON_DAYS}, got {custom_horizon_days}")
    elif custom_horizon_days is not None:
        raise InvalidPreferenceError("custom_horizon_days must be omitted unless horizon_band is CUSTOM")

    if risk_preference not in VALID_RISK_PREFERENCES:
        raise InvalidPreferenceError(f"risk_preference must be one of {VALID_RISK_PREFERENCES}, got {risk_preference!r}")

    if not (Decimal("0") <= min_confidence_threshold <= Decimal("1")):
        raise InvalidPreferenceError(f"min_confidence_threshold must be within [0, 1], got {min_confidence_threshold}")

    if preferred_market_cap_buckets is not None:
        invalid = set(preferred_market_cap_buckets) - VALID_MARKET_CAP_BUCKETS
        if invalid:
            raise InvalidPreferenceError(f"preferred_market_cap_buckets contains unknown bucket(s): {sorted(invalid)}")


def set_user_preference(
    session: Session,
    *,
    user_id: str,
    effective_at: datetime,
    horizon_band: str = DEFAULT_HORIZON_BAND,
    custom_horizon_days: int | None = None,
    risk_preference: str = DEFAULT_RISK_PREFERENCE,
    min_confidence_threshold: Decimal = DEFAULT_MIN_CONFIDENCE_THRESHOLD,
    preferred_sectors: list | None = None,
    preferred_market_cap_buckets: list | None = None,
) -> UserPreference:
    """Always inserts a new preference version -- never updates a prior one
    (AC: "a user can change horizon and supported preferences" without
    mutating history). Raises `InvalidPreferenceError` for any structurally
    invalid combination (AC: "invalid preference combinations are rejected
    clearly") before anything is written."""
    _validate_preference(
        horizon_band=horizon_band,
        custom_horizon_days=custom_horizon_days,
        risk_preference=risk_preference,
        min_confidence_threshold=min_confidence_threshold,
        preferred_market_cap_buckets=preferred_market_cap_buckets,
    )

    preference = UserPreference(
        user_id=user_id,
        horizon_band=horizon_band,
        custom_horizon_days=custom_horizon_days,
        risk_preference=risk_preference,
        min_confidence_threshold=min_confidence_threshold,
        preferred_sectors=preferred_sectors,
        preferred_market_cap_buckets=preferred_market_cap_buckets,
        effective_at=effective_at,
        preference_rule_version=PREFERENCE_RULE_VERSION,
    )
    session.add(preference)
    session.commit()
    session.refresh(preference)
    return preference


def get_current_preference(session: Session, user_id: str, *, effective_at: datetime) -> UserPreference:
    """Returns the most recently set preference for `user_id`, or lazily
    creates and returns a real, persisted default preference row if this
    user has never set one (AC: "new users default to short-term 1-7 day
    recommendations") -- idempotent: a second call for the same never-set
    user returns the same row created by the first call, never a second
    default."""
    existing = session.scalar(
        select(UserPreference).where(UserPreference.user_id == user_id).order_by(UserPreference.id.desc())
    )
    if existing is not None:
        return existing
    return set_user_preference(session, user_id=user_id, effective_at=effective_at)


def _horizon_range(preference: UserPreference) -> tuple[int, int | None]:
    if preference.horizon_band == HORIZON_BAND_CUSTOM:
        return preference.custom_horizon_days, preference.custom_horizon_days
    return HORIZON_BAND_DAY_RANGES[preference.horizon_band]


def _matches_horizon(preference: UserPreference, horizon_days: int) -> bool:
    lower, upper = _horizon_range(preference)
    if horizon_days < lower:
        return False
    return upper is None or horizon_days <= upper


def apply_preferences_to_scan_selection(
    session: Session,
    *,
    user_id: str,
    scan_id: int,
    snapshotted_at: datetime,
) -> tuple[RecommendationPreferenceSnapshot, ...]:
    """Personalizes M1.14's already-selected, system-wide daily picks for
    one user -- never re-ranks or re-selects them system-wide, and never
    touches `RecommendationSelection`/`Prediction`/`ScanCandidate` (scope:
    "apply preferences consistently to discovery and recommendation
    selection" without changing the underlying recommendation contract).
    Idempotent per `(user_id, recommendation_generation_id)`: a recommendation
    already snapshotted for this user returns its original snapshot
    unchanged, even if the user's preference has since changed (AC:
    "preference changes do not mutate historical recommendations")."""
    preference = get_current_preference(session, user_id, effective_at=snapshotted_at)

    selections = select_recommendations_for_scan(session, scan_id)
    selected_generation_ids = [s.recommendation_generation_id for s in selections if s.selected]
    if not selected_generation_ids:
        return ()

    existing_by_generation_id = {
        row.recommendation_generation_id: row
        for row in session.scalars(
            select(RecommendationPreferenceSnapshot).where(
                RecommendationPreferenceSnapshot.user_id == user_id,
                RecommendationPreferenceSnapshot.recommendation_generation_id.in_(selected_generation_ids),
            )
        ).all()
    }

    rows = session.execute(
        select(RecommendationGeneration, ScanCandidate, Stock, Prediction)
        .join(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
        .join(Stock, Stock.id == ScanCandidate.stock_id)
        .join(Prediction, Prediction.id == RecommendationGeneration.prediction_id)
        .where(RecommendationGeneration.id.in_(selected_generation_ids))
    ).all()

    snapshots: list[RecommendationPreferenceSnapshot] = []
    for generation, scan_candidate, stock, prediction in rows:
        if generation.id in existing_by_generation_id:
            snapshots.append(existing_by_generation_id[generation.id])
            continue

        matched_horizon = _matches_horizon(preference, prediction.horizon_days)
        met_min_confidence = scan_candidate.confidence >= preference.min_confidence_threshold

        preferred_sectors = preference.preferred_sectors or []
        preferred_buckets = preference.preferred_market_cap_buckets or []
        preference_match_boost = bool(
            (stock.sector is not None and stock.sector in preferred_sectors)
            or (preferred_buckets and classify_market_cap_bucket(stock.market_cap) in preferred_buckets)
        )

        if not matched_horizon:
            included, exclusion_reason = False, REASON_NOT_IN_HORIZON_BAND
        elif not met_min_confidence:
            included, exclusion_reason = False, REASON_BELOW_MIN_CONFIDENCE
        else:
            included, exclusion_reason = True, None

        snapshot = RecommendationPreferenceSnapshot(
            user_id=user_id,
            recommendation_generation_id=generation.id,
            user_preference_id=preference.id,
            horizon_band=preference.horizon_band,
            min_confidence_threshold=preference.min_confidence_threshold,
            matched_horizon=matched_horizon,
            met_min_confidence=met_min_confidence,
            preference_match_boost=preference_match_boost,
            included=included,
            exclusion_reason=exclusion_reason,
            snapshotted_at=snapshotted_at,
            preference_rule_version=PREFERENCE_RULE_VERSION,
        )
        session.add(snapshot)
        snapshots.append(snapshot)

    session.commit()
    for snapshot in snapshots:
        if snapshot not in existing_by_generation_id.values():
            session.refresh(snapshot)
    return tuple(snapshots)
