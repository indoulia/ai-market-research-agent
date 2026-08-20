from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import MarketPrice, Stock
from .upstox import UpstoxClient


def upsert_nse_universe(session: Session, instruments: Iterable[dict]) -> int:
    """Upsert NSE equity instruments while preserving the local stock id."""
    count = 0
    for instrument in instruments:
        symbol = instrument["trading_symbol"].strip().upper()
        key = instrument["instrument_key"]
        values = {
            "symbol": symbol,
            "instrument_key": key,
            "exchange": instrument.get("exchange", "NSE"),
            "company_name": instrument.get("name"),
            "is_active": True,
        }
        existing = session.scalar(select(Stock).where(Stock.symbol == symbol))
        if existing:
            for field, value in values.items():
                setattr(existing, field, value)
        else:
            session.add(Stock(**values))
        count += 1
    session.commit()
    return count


def ingest_daily_history(
    session: Session,
    client: UpstoxClient,
    from_date: date,
    to_date: date,
    symbols: Iterable[str] | None = None,
) -> int:
    """Fetch and idempotently persist daily OHLCV candles for active NSE stocks."""
    query = select(Stock).where(Stock.is_active.is_(True), Stock.instrument_key.is_not(None))
    if symbols:
        normalized = [symbol.strip().upper() for symbol in symbols]
        query = query.where(Stock.symbol.in_(normalized))
    stocks = session.scalars(query.order_by(Stock.symbol)).all()
    inserted = 0

    for stock in stocks:
        candles = client.fetch_daily_candles(stock.instrument_key, from_date, to_date)
        for candle in candles:
            if len(candle) < 6:
                continue
            timestamp = datetime.fromisoformat(candle[0])
            open_price, high, low, close, volume = candle[1:6]
            if min(open_price, high, low, close) < 0 or volume < 0:
                continue
            stmt = insert(MarketPrice).values(
                stock_id=stock.id,
                timestamp=timestamp,
                open=Decimal(str(open_price)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=int(volume),
                source="upstox-v3",
            ).on_conflict_do_nothing(index_elements=["stock_id", "timestamp"])
            result = session.execute(stmt)
            inserted += result.rowcount or 0
        session.commit()
    return inserted
