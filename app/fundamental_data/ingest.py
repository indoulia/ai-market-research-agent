"""EPIC-M1.72: provider-agnostic fundamental-data ingestion orchestration.

Mirrors `app.market_data.ingest`'s own provider-boundary pattern (a
`Protocol`, a concrete adapter, and an orchestration function that never
imports the concrete adapter directly) so a future licensed provider can
be swapped in without touching this module or `app.evidence_snapshot`.

Point-in-time safety (AC: "historical recommendations can only see
fundamentals available at their decision time") is enforced entirely by
`get_latest_fundamental_record`'s own `published_at <= as_of_timestamp`
filter -- a later revision is simply a separate, later-published row that
this filter will not surface for an earlier `as_of_timestamp` (AC:
"revisions do not mutate prior evidence snapshots" -- nothing here ever
updates an existing `FundamentalDataRecord`).
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Protocol

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .yahoo import RawFundamentals
from ..models import FundamentalDataRecord, Stock
from ..refresh_policy import DATA_TYPE_FUNDAMENTAL, check_fundamental_data_freshness, record_fetch_attempt

FUNDAMENTAL_INGESTION_VERSION = "FDI-001"

FAILURE_NO_DATA_RETURNED = "no_data_returned"


class FundamentalDataRecordImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "stock_id",
    "source",
    "period_end_date",
    "revenue",
    "net_income",
    "eps",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "debt_to_equity",
    "free_cash_flow",
    "pe_ratio",
    "price_to_book",
    "published_at",
    "fetched_at",
    "ingestion_rule_version",
    "created_at",
)


@event.listens_for(FundamentalDataRecord, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise FundamentalDataRecordImmutableError(
            f"fundamental data record {target.id} field(s) {changed} cannot be modified after creation -- "
            "ingest a new revision instead"
        )


class FundamentalDataProvider(Protocol):
    source: str

    def fetch_fundamentals(self, symbol: str) -> RawFundamentals | None: ...


def get_latest_fundamental_record(
    session: Session, stock_id: int, *, as_of_timestamp: datetime
) -> FundamentalDataRecord | None:
    """The one, point-in-time-safe read path every consumer (including
    `app.evidence_snapshot`) must use -- never a plain "most recent row"
    query, which would leak future revisions into a historical decision."""
    return session.scalar(
        select(FundamentalDataRecord)
        .where(FundamentalDataRecord.stock_id == stock_id, FundamentalDataRecord.published_at <= as_of_timestamp)
        .order_by(FundamentalDataRecord.published_at.desc())
    )


def ingest_fundamental_data(
    session: Session,
    provider: FundamentalDataProvider,
    stock: Stock,
    *,
    requested_at: datetime,
) -> FundamentalDataRecord | None:
    """Fetches and persists one stock's latest available fundamentals.
    Skips the provider call entirely -- "avoid unnecessary duplicate
    fetches" -- when existing data is already fresh under M1.35's own
    90-day `DATA_TYPE_FUNDAMENTAL` policy; returns that existing,
    point-in-time-valid record unchanged. Every real attempt, successful
    or failed, is recorded via M1.35's `record_fetch_attempt` (scope:
    "record fetch attempts, freshness, source, completeness and
    failures")."""
    already_fresh = check_fundamental_data_freshness(session, stock.id, requested_at)
    if already_fresh.is_fresh:
        return get_latest_fundamental_record(session, stock.id, as_of_timestamp=requested_at)

    try:
        raw = provider.fetch_fundamentals(stock.symbol)
    except Exception as exc:
        record_fetch_attempt(
            session, data_type=DATA_TYPE_FUNDAMENTAL, scope_key=str(stock.id), requested_at=requested_at,
            source_timestamp=None, success=False, failure_reason=str(exc),
        )
        return None

    if raw is None:
        record_fetch_attempt(
            session, data_type=DATA_TYPE_FUNDAMENTAL, scope_key=str(stock.id), requested_at=requested_at,
            source_timestamp=None, success=False, failure_reason=FAILURE_NO_DATA_RETURNED,
        )
        return None

    # Point-in-time anchor: the fiscal period's own end date when the
    # provider reports one, else the honest, conservative fallback -- the
    # moment we actually observed it -- never a fabricated earlier date.
    published_at = (
        datetime.combine(raw.period_end_date, time.min, tzinfo=timezone.utc)
        if raw.period_end_date is not None
        else requested_at
    )

    record_fetch_attempt(
        session, data_type=DATA_TYPE_FUNDAMENTAL, scope_key=str(stock.id), requested_at=requested_at,
        source_timestamp=published_at, success=True,
    )

    record = FundamentalDataRecord(
        stock_id=stock.id,
        source=getattr(provider, "source", "unknown"),
        period_end_date=raw.period_end_date,
        revenue=raw.revenue,
        net_income=raw.net_income,
        eps=raw.eps,
        gross_margin=raw.gross_margin,
        operating_margin=raw.operating_margin,
        net_margin=raw.net_margin,
        debt_to_equity=raw.debt_to_equity,
        free_cash_flow=raw.free_cash_flow,
        pe_ratio=raw.pe_ratio,
        price_to_book=raw.price_to_book,
        published_at=published_at,
        fetched_at=requested_at,
        ingestion_rule_version=FUNDAMENTAL_INGESTION_VERSION,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
