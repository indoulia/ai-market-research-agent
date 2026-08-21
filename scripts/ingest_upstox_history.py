from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

from app.db import SessionLocal
from app.market_data import UpstoxClient
from app.market_data.ingest import ingest_daily_history, upsert_nse_universe
from app.settings import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Load NSE universe and daily Upstox history")
    parser.add_argument("--from-date", required=True, type=date.fromisoformat)
    parser.add_argument("--to-date", required=True, type=date.fromisoformat)
    parser.add_argument("--symbol", action="append", dest="symbols")
    args = parser.parse_args()

    if not settings.upstox_access_token:
        raise SystemExit("UPSTOX_ACCESS_TOKEN is required")

    with UpstoxClient(settings.upstox_access_token, settings.upstox_instruments_url) as client:
        with SessionLocal() as session:
            universe_count = upsert_nse_universe(session, client.fetch_nse_instruments())
            candle_count = ingest_daily_history(
                session,
                client,
                args.from_date,
                args.to_date,
                args.symbols,
                requested_at=datetime.now(timezone.utc),
            )
    print(f"NSE instruments upserted: {universe_count}")
    print(f"Daily candles inserted: {candle_count}")


if __name__ == "__main__":
    main()
