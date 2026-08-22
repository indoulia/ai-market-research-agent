from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

from app.db import SessionLocal
from app.market_data import UpstoxClient
from app.market_data.ingest import ingest_daily_history, upsert_nse_universe
from app.settings import settings
from app.upstox_oauth import resolve_access_token


def main() -> None:
    parser = argparse.ArgumentParser(description="Load NSE universe and daily Upstox history")
    parser.add_argument("--from-date", required=True, type=date.fromisoformat)
    parser.add_argument("--to-date", required=True, type=date.fromisoformat)
    parser.add_argument("--symbol", action="append", dest="symbols")
    args = parser.parse_args()

    requested_at = datetime.now(timezone.utc)
    with SessionLocal() as session:
        access_token = resolve_access_token(session, at=requested_at)
        if not access_token:
            raise SystemExit(
                "No usable Upstox access token: complete the OAuth login "
                "(GET /api/v1/integrations/upstox/authorize) or set UPSTOX_ACCESS_TOKEN"
            )
        with UpstoxClient(access_token, settings.upstox_instruments_url) as client:
            universe_count = upsert_nse_universe(session, client.fetch_nse_instruments())
            candle_count = ingest_daily_history(
                session,
                client,
                args.from_date,
                args.to_date,
                args.symbols,
                requested_at=requested_at,
            )
    print(f"NSE instruments upserted: {universe_count}")
    print(f"Daily candles inserted: {candle_count}")


if __name__ == "__main__":
    main()
