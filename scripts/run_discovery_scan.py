"""Run one operational discovery scan against persisted market data."""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import select

from app.baseline_signal_provider import MODEL_VERSION, TechnicalBaselineSignalProvider
from app.db import SessionLocal
from app.market_data.quality import NSE_TIMEZONE
from app.models import MarketPrice, Stock
from app.continuous_discovery import run_scheduled_discovery_scan


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _entry_price_for(session, scan_date: date):
    cutoff = datetime.combine(scan_date, time.max, NSE_TIMEZONE)

    def resolve(stock_id: int) -> Decimal:
        row = session.scalar(
            select(MarketPrice.close)
            .where(MarketPrice.stock_id == stock_id, MarketPrice.timestamp <= cutoff)
            .order_by(MarketPrice.timestamp.desc())
            .limit(1)
        )
        if row is None:
            raise RuntimeError(f"No entry price available for stock_id={stock_id} on {scan_date}")
        return Decimal(row)

    return resolve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the M1.149 one-shot discovery scan")
    parser.add_argument("--scan-date", type=_parse_date, default=None, help="NSE scan date (YYYY-MM-DD)")
    parser.add_argument("--target-return", type=Decimal, default=Decimal("0.05"))
    parser.add_argument("--stop-return", type=Decimal, default=Decimal("-0.03"))
    parser.add_argument("--min-score", type=Decimal, default=None)
    parser.add_argument("--daily-limit", type=int, default=10)
    parser.add_argument(
        "--signal-provider",
        choices=("baseline-technical-v1",),
        default="baseline-technical-v1",
        help="Executable signal provider; production model providers can be added later without changing scan orchestration.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    scan_date = args.scan_date or datetime.now(NSE_TIMEZONE).date()

    if args.signal_provider != MODEL_VERSION:
        raise SystemExit(f"Unsupported signal provider: {args.signal_provider}")

    provider = TechnicalBaselineSignalProvider()
    with SessionLocal() as session:
        active_stocks = session.scalar(
            select(Stock.id).where(Stock.is_active.is_(True)).limit(1)
        )
        market_rows = session.scalar(select(MarketPrice.id).limit(1))
        if active_stocks is None or market_rows is None:
            print(
                f"discovery_scan status=empty_data scan_date={scan_date.isoformat()} "
                "stocks_or_market_prices_missing=1 candidates=0 discoveries=0"
            )
            return 0

        result = run_scheduled_discovery_scan(
            session,
            scan_date=scan_date,
            signal_provider=provider,
            as_of_timestamp=datetime.now(timezone.utc),
            entry_price_for=_entry_price_for(session, scan_date),
            target_return=args.target_return,
            stop_return=args.stop_return,
            min_score=args.min_score if args.min_score is not None else Decimal("0"),
            daily_limit=args.daily_limit,
        )

        eligible = sum(1 for candidate in result.scan and session.scalars(
            select(__import__("app.models", fromlist=["ScanCandidate"]).ScanCandidate)
            .where(__import__("app.models", fromlist=["ScanCandidate"]).ScanCandidate.scan_id == result.scan.id)
        ).all() if candidate.eligible)
        print(
            "discovery_scan "
            f"status=success scan_date={scan_date.isoformat()} "
            f"model_version={provider.model_version} "
            f"candidates={len(result.scan and result.discovery_records)} "
            f"discoveries={len(result.discovery_records)} "
            f"generations={len(result.generations)} "
            f"selections={len(result.selections)} "
            f"eligible={eligible}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
