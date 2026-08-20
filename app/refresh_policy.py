"""EPIC-M1.35: determine what information must be fetched, when it must be
refreshed, and when existing data is sufficiently fresh for analysis.

This repo currently only has one real data type actually ingested end to
end -- market/price data (`MarketPrice`, via `app/market_data/`). There is
no news/event or fundamental-data ingestion pipeline in this codebase yet.
Fabricating fetch logic for data that isn't really ingested would violate
this platform's standing rule against fabricated evidence, so this module
defines the policy framework generically (a `data_type` dimension with a
fixed, documented, versioned freshness threshold per type) and provides a
working, tested instantiation for market data -- the one type genuinely
backed by real ingestion -- while news/event and fundamental-data remain
named policy constants only, honestly representing what this platform can
actually determine "fresh enough" for today.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .models import DataFetchAttempt, MarketPrice

REFRESH_POLICY_VERSION = "RFP-001"

DATA_TYPE_MARKET = "MARKET_DATA"
DATA_TYPE_NEWS_EVENT = "NEWS_EVENT"
DATA_TYPE_FUNDAMENTAL = "FUNDAMENTAL_DATA"

# Fixed, documented, versioned freshness policy per data type: the maximum
# gap between a data type's source timestamp and the as-of moment analysis
# needs it, before that data is considered too stale to use. NEWS_EVENT and
# FUNDAMENTAL_DATA are defined so the framework is provably generic, even
# though no ingestion path in this repo produces their source timestamps yet.
FRESHNESS_POLICY = {
    DATA_TYPE_MARKET: timedelta(days=1),
    DATA_TYPE_NEWS_EVENT: timedelta(hours=6),
    DATA_TYPE_FUNDAMENTAL: timedelta(days=90),
}

REASON_MISSING_DATA = "missing_data"
REASON_STALE_DATA = "stale_data"


class UnsupportedDataTypeError(RuntimeError):
    pass


class DataFetchAttemptImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "data_type",
    "scope_key",
    "requested_at",
    "source_timestamp",
    "success",
    "failure_reason",
    "refresh_policy_version",
    "created_at",
)


@event.listens_for(DataFetchAttempt, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise DataFetchAttemptImmutableError(
            f"data fetch attempt {target.id} field(s) {changed} cannot be modified after creation"
        )


@dataclass(frozen=True)
class FreshnessCheck:
    data_type: str
    as_of_timestamp: datetime
    source_timestamp: datetime | None
    is_fresh: bool
    staleness: timedelta | None
    reason: str | None


def is_data_fresh(
    data_type: str, source_timestamp: datetime | None, as_of_timestamp: datetime
) -> FreshnessCheck:
    """Deterministic freshness decision for one data type. Missing data
    (`source_timestamp=None`) is always explicitly `missing_data`, never
    silently treated as fresh or stale by a fabricated default."""
    policy = FRESHNESS_POLICY.get(data_type)
    if policy is None:
        raise UnsupportedDataTypeError(f"no freshness policy defined for data type: {data_type}")

    if source_timestamp is None:
        return FreshnessCheck(
            data_type=data_type,
            as_of_timestamp=as_of_timestamp,
            source_timestamp=None,
            is_fresh=False,
            staleness=None,
            reason=REASON_MISSING_DATA,
        )

    # sqlite drops tzinfo on DateTime(timezone=True) round-trips, unlike
    # Postgres; every timestamp in this system is UTC-based by convention, so
    # comparing naively is correct regardless of which backend produced the
    # value.
    staleness = as_of_timestamp.replace(tzinfo=None) - source_timestamp.replace(tzinfo=None)
    if staleness > policy:
        return FreshnessCheck(
            data_type=data_type,
            as_of_timestamp=as_of_timestamp,
            source_timestamp=source_timestamp,
            is_fresh=False,
            staleness=staleness,
            reason=REASON_STALE_DATA,
        )

    return FreshnessCheck(
        data_type=data_type,
        as_of_timestamp=as_of_timestamp,
        source_timestamp=source_timestamp,
        is_fresh=True,
        staleness=staleness,
        reason=None,
    )


def check_market_data_freshness(session: Session, stock_id: int, as_of_timestamp: datetime) -> FreshnessCheck:
    """The one real, working instantiation of the policy: is the latest
    ingested `MarketPrice` row for this stock fresh enough as of
    `as_of_timestamp`?"""
    latest_timestamp = session.scalar(
        select(MarketPrice.timestamp)
        .where(MarketPrice.stock_id == stock_id)
        .order_by(MarketPrice.timestamp.desc())
    )
    return is_data_fresh(DATA_TYPE_MARKET, latest_timestamp, as_of_timestamp)


def record_fetch_attempt(
    session: Session,
    *,
    data_type: str,
    scope_key: str,
    requested_at: datetime,
    source_timestamp: datetime | None,
    success: bool,
    failure_reason: str | None = None,
) -> DataFetchAttempt:
    """Record one refresh attempt. Avoids an unnecessary duplicate fetch
    (scope item: "avoid unnecessary duplicate fetches"): if the most recent
    successful attempt for `(data_type, scope_key)` is already fresh enough
    as of `requested_at` under this data type's own policy, that existing
    attempt is returned unchanged rather than recording a redundant one.
    Every recorded attempt (successful or failed) is immutable once created
    -- there is no update path in this module at all, only inserts."""
    if data_type not in FRESHNESS_POLICY:
        raise UnsupportedDataTypeError(f"no freshness policy defined for data type: {data_type}")

    existing = session.scalar(
        select(DataFetchAttempt)
        .where(
            DataFetchAttempt.data_type == data_type,
            DataFetchAttempt.scope_key == scope_key,
            DataFetchAttempt.success.is_(True),
        )
        .order_by(DataFetchAttempt.id.desc())
    )
    if existing is not None:
        check = is_data_fresh(data_type, existing.source_timestamp, requested_at)
        if check.is_fresh:
            return existing

    attempt = DataFetchAttempt(
        data_type=data_type,
        scope_key=scope_key,
        requested_at=requested_at,
        source_timestamp=source_timestamp,
        success=success,
        failure_reason=failure_reason,
        refresh_policy_version=REFRESH_POLICY_VERSION,
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def get_fetch_history(session: Session, *, data_type: str, scope_key: str) -> tuple[DataFetchAttempt, ...]:
    return tuple(
        session.scalars(
            select(DataFetchAttempt)
            .where(DataFetchAttempt.data_type == data_type, DataFetchAttempt.scope_key == scope_key)
            .order_by(DataFetchAttempt.id.asc())
        ).all()
    )
