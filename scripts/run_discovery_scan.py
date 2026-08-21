"""EPIC-M1.149: the one documented, deterministic entrypoint that turns already
-ingested market data into real `scan_candidates` and `discovery_records` -- the
operational gap between `scripts/ingest_market_history.py` and the discovery
API/UI. Composes `app.continuous_discovery.run_scheduled_discovery_scan`
verbatim; this script only resolves configuration (which SignalProvider, which
scan date, which target/stop return) and reports a machine-readable summary. It
never fabricates a discovery record: a data or configuration gap is reported as
an explicit zero-result run or an operational failure, never worked around.

Usage (native):
    python -m scripts.run_discovery_scan
    python -m scripts.run_discovery_scan --scan-date 2026-08-21

Usage (Docker Compose, on-demand service, not started by `docker compose up`):
    docker compose run --rm discovery
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.continuous_discovery import run_scheduled_discovery_scan
from app.db import SessionLocal
from app.market_data.quality import NSE_TIMEZONE
from app.models import MarketPrice, ScanCandidate, Stock
from app.recommendation_selection import DEFAULT_DAILY_LIMIT, MIN_SCORE_FOR_SELECTION
from app.scan import SignalProvider
from app.settings import settings

PROVIDER_BASELINE = "baseline"


class DiscoveryScanConfigurationError(SystemExit):
    """Raised for a configuration problem (e.g. an unresolvable
    SignalProvider) -- distinct from an ordinary empty-data run, which is not
    an error."""


def _resolve_signal_provider(name: str) -> SignalProvider:
    key = name.strip().lower()
    if key == PROVIDER_BASELINE:
        from app.baseline_signal import BaselineSignalProvider

        return BaselineSignalProvider()
    raise DiscoveryScanConfigurationError(
        f"Unknown DISCOVERY_SIGNAL_PROVIDER '{name}' (expected '{PROVIDER_BASELINE}'); "
        "refusing to run a discovery scan without a resolvable SignalProvider."
    )


def _latest_close_prices_by_stock(session, cutoff: datetime) -> dict[int, Decimal]:
    """One real close price per stock, as of the same `timestamp <= cutoff`
    cutoff `run_daily_candidate_scan` used to build that stock's features --
    never fabricated, never a different session than what was scored."""
    latest_ts = (
        select(MarketPrice.stock_id, func.max(MarketPrice.timestamp).label("ts"))
        .where(MarketPrice.timestamp <= cutoff)
        .group_by(MarketPrice.stock_id)
        .subquery()
    )
    rows = session.execute(
        select(MarketPrice.stock_id, MarketPrice.close).join(
            latest_ts,
            (MarketPrice.stock_id == latest_ts.c.stock_id) & (MarketPrice.timestamp == latest_ts.c.ts),
        )
    ).all()
    return {stock_id: close for stock_id, close in rows}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one deterministic discovery scan against already-persisted market data: "
            "resolve the configured SignalProvider, scan the active universe, and persist "
            "real scan_candidates/discovery_records. Safe to re-run for the same scan date."
        )
    )
    parser.add_argument(
        "--scan-date",
        type=date.fromisoformat,
        default=None,
        help="Trading date to scan, YYYY-MM-DD (default: today in NSE time).",
    )
    parser.add_argument(
        "--as-of",
        type=datetime.fromisoformat,
        default=None,
        help="Point-in-time timestamp recorded on the resulting discovery/generation rows (default: now, UTC).",
    )
    parser.add_argument("--target-return", type=Decimal, default=settings.discovery_target_return)
    parser.add_argument("--stop-return", type=Decimal, default=settings.discovery_stop_return)
    parser.add_argument("--min-score", type=Decimal, default=MIN_SCORE_FOR_SELECTION)
    parser.add_argument("--daily-limit", type=int, default=DEFAULT_DAILY_LIMIT)
    return parser.parse_args(argv)


def run_scan(
    session,
    *,
    scan_date: date,
    as_of: datetime,
    signal_provider: SignalProvider,
    target_return: Decimal,
    stop_return: Decimal,
    min_score: Decimal = MIN_SCORE_FOR_SELECTION,
    daily_limit: int = DEFAULT_DAILY_LIMIT,
    provider_name: str | None = None,
) -> dict:
    """The testable core: everything `run()` does once a session and a
    resolved `SignalProvider` exist. Kept separate from `run()` so tests can
    exercise it against an in-memory session the same way every other
    discovery-pipeline test in this repo does, without touching `app.db`."""
    cutoff = datetime.combine(scan_date, time.min, NSE_TIMEZONE)

    active_stock_count = (
        session.scalar(select(func.count()).select_from(Stock).where(Stock.is_active.is_(True))) or 0
    )
    input_row_count = (
        session.scalar(select(func.count()).select_from(MarketPrice).where(MarketPrice.timestamp <= cutoff)) or 0
    )
    entry_prices = _latest_close_prices_by_stock(session, cutoff)

    def entry_price_for(stock_id: int) -> Decimal:
        price = entry_prices.get(stock_id)
        if price is None:
            # Cannot happen for an eligible candidate: eligibility already
            # requires a MarketPrice row at/before `cutoff` (app/scan.py).
            # Surfaced loudly rather than silently defaulting a price.
            raise DiscoveryScanConfigurationError(
                f"eligible candidate stock_id={stock_id} has no market price at/before {cutoff.isoformat()}"
            )
        return price

    result = run_scheduled_discovery_scan(
        session,
        scan_date,
        signal_provider,
        as_of_timestamp=as_of,
        entry_price_for=entry_price_for,
        target_return=target_return,
        stop_return=stop_return,
        min_score=min_score,
        daily_limit=daily_limit,
    )

    excluded_by_reason: dict[str, int] = {}
    reason_rows = session.execute(
        select(ScanCandidate.exclusion_reason, func.count())
        .where(ScanCandidate.scan_id == result.scan.id, ScanCandidate.eligible.is_(False))
        .group_by(ScanCandidate.exclusion_reason)
    ).all()
    for reason, count in reason_rows:
        excluded_by_reason[reason or "unknown"] = count

    summary = {
        "scan_date": scan_date.isoformat(),
        "universe_version": result.scan.universe_version,
        "signal_provider": provider_name or settings.discovery_signal_provider,
        "model_version": signal_provider.model_version,
        "active_stocks": active_stock_count,
        "input_market_price_rows": input_row_count,
        "candidates_eligible": result.scan.eligible_count,
        "candidates_excluded": result.scan.excluded_count,
        "candidates_excluded_by_reason": excluded_by_reason,
        "discovery_records_created": len(result.discovery_records),
        "recommendation_generations_created": len(result.generations),
        "recommendations_selected": sum(1 for selection in result.selections if selection.selected),
        "status": "ok" if input_row_count > 0 else "no_market_data",
    }
    return summary


def run(argv: list[str] | None = None) -> dict:
    args = _parse_args(argv)

    as_of = args.as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    scan_date = args.scan_date or as_of.astimezone(NSE_TIMEZONE).date()

    signal_provider = _resolve_signal_provider(settings.discovery_signal_provider)

    with SessionLocal() as session:
        summary = run_scan(
            session,
            scan_date=scan_date,
            as_of=as_of,
            signal_provider=signal_provider,
            target_return=args.target_return,
            stop_return=args.stop_return,
            min_score=args.min_score,
            daily_limit=args.daily_limit,
            provider_name=settings.discovery_signal_provider,
        )

    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    run()


if __name__ == "__main__":
    main()
