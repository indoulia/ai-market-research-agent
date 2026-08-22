from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

from app.db import SessionLocal
from app.market_data import UpstoxClient, YahooFinanceClient
from app.market_data.ingest import ingest_daily_history, upsert_nse_universe
from app.settings import settings
from app.upstox_oauth import resolve_access_token

PROVIDER_UPSTOX = "upstox"
PROVIDER_YAHOO = "yahoo"


def _yahoo_instruments(symbols: list[str]) -> list[dict]:
    # Yahoo has no NSE instrument-master endpoint (unlike Upstox), so the
    # universe is exactly the configured symbol list.
    return [
        {"trading_symbol": symbol, "instrument_key": f"{symbol}.NS", "exchange": "NSE", "name": symbol}
        for symbol in symbols
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load the NSE universe and daily history from whichever provider MARKET_DATA_PROVIDER selects."
    )
    parser.add_argument("--from-date", required=True, type=date.fromisoformat)
    parser.add_argument("--to-date", required=True, type=date.fromisoformat)
    parser.add_argument("--symbol", action="append", dest="symbols")
    args = parser.parse_args()

    provider = settings.market_data_provider.strip().lower()
    requested_at = datetime.now(timezone.utc)

    with SessionLocal() as session:
        if provider == PROVIDER_YAHOO:
            symbols = args.symbols or [s.strip().upper() for s in settings.yahoo_symbols.split(",") if s.strip()]
            if not symbols:
                raise SystemExit("YAHOO_SYMBOLS (or --symbol) is required when MARKET_DATA_PROVIDER=yahoo")
            client = YahooFinanceClient()
            universe_count = upsert_nse_universe(session, _yahoo_instruments(symbols))
            candle_count = ingest_daily_history(
                session, client, args.from_date, args.to_date, symbols, requested_at=requested_at,
            )
        elif provider == PROVIDER_UPSTOX:
            access_token = resolve_access_token(session, at=requested_at)
            if not access_token:
                raise SystemExit(
                    "No usable Upstox access token: complete the OAuth login "
                    "(GET /api/v1/integrations/upstox/authorize) or set UPSTOX_ACCESS_TOKEN"
                )
            with UpstoxClient(access_token, settings.upstox_instruments_url) as client:
                universe_count = upsert_nse_universe(session, client.fetch_nse_instruments())
                candle_count = ingest_daily_history(
                    session, client, args.from_date, args.to_date, args.symbols, requested_at=requested_at,
                )
        else:
            raise SystemExit(f"Unknown MARKET_DATA_PROVIDER '{provider}' (expected '{PROVIDER_UPSTOX}' or '{PROVIDER_YAHOO}')")

    print(f"Provider: {provider}")
    print(f"NSE instruments upserted: {universe_count}")
    print(f"Daily candles inserted: {candle_count}")


if __name__ == "__main__":
    main()
