"""Run one operational discovery scan against persisted market data."""
from __future__ import annotations

import argparse
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import func, select

from app.baseline_signal_provider import MODEL_VERSION, TechnicalBaselineSignalProvider
from app.continuous_discovery import run_scheduled_discovery_scan
from app.db import SessionLocal
from app.market_data.quality import NSE_TIMEZONE
from app.models import MarketPrice, ScanCandidate, Stock
from app.recommendation_selection import MIN_SCORE_FOR_SELECTION


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _latest_market_session(session) -> date | None:
    latest = session.scalar(select(func.max(MarketPrice.timestamp)))
    return latest.astimezone(NSE_TIMEZONE).date() if latest is not None else None


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
    parser.add_argument("--scan-date", type=_parse_date, default=None, help="NSE scan date (YYYY-MM-DD); defaults to latest persisted market session")
    parser.add_argument("--target-return", type=Decimal, default=Decimal("0.05"))
    parser.add_argument("--stop-return", type=Decimal, default=Decimal("-0.03"))
    parser.add_argument("--min-score", type=Decimal, default=MIN_SCORE_FOR_SELECTION)
    parser.add_argument("--daily-limit", type=int, default=10)
    parser.add_argument(
        "--signal-provider",
        choices=(MODEL_VERSION,),
        default=MODEL_VERSION,
        help="Executable signal provider; production model providers can be added later without changing scan orchestration.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.signal_provider != MODEL_VERSION:
        raise SystemExit(f"Unsupported signal provider: {args.signal_provider}")

    provider = TechnicalBaselineSignalProvider()
    with SessionLocal() as session:
        active_stock_count = session.scalar(
            select(func.count()).select_from(Stock).where(Stock.is_active.is_(True))
        )
        latest_session = _latest_market_session(session)
        if active_stock_count == 0 or latest_session is None:
            print(
                "discovery_scan "
                "status=empty_data "
                f"stocks={active_stock_count or 0} market_sessions=0 candidates=0 discoveries=0"
            )
            return 0

        scan_date = args.scan_date or latest_session
        as_of_timestamp = datetime.combine(scan_date, time.max, NSE_TIMEZONE).astimezone().astimezone(__import__("datetime").timezone.utc)
        result = run_scheduled_discovery_scan(
            session,
            scan_date=scan_date,
            signal_provider=provider,
            as_of_timestamp=as_of_timestamp,
            entry_price_for=_entry_price_for(session, scan_date),
            target_return=args.target_return,
            stop_return=args.stop_return,
            min_score=args.min_score,
            daily_limit=args.daily_limit,
        )

        candidates = session.scalars(
            select(ScanCandidate).where(ScanCandidate.scan_id == result.scan.id)
        ).all()
        eligible = sum(candidate.eligible for candidate in candidates)
        print(
            "discovery_scan "
            f"status=success scan_date={scan_date.isoformat()} "
            f"model_version={provider.model_version} "
            f"candidates={len(candidates)} eligible={eligible} "
            f"discoveries={len(result.discovery_records)} "
            f"generations={len(result.generations)} "
            f"selections={len(result.selections)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
