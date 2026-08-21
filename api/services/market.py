"""Query service backing GET /api/v1/market/summary (EPIC-M1.139).

Composes existing data rather than inventing a new domain module:
  - M1.30's `MarketRegime` (latest by scan date) for `regime` and
    `advanceDecline` (`breadth_positive_ratio`) and `volatility`
    (`average_atr_percent`).
  - Raw `MarketPrice` for `volume` (real SUM across the universe on the
    latest available trading day) and `sectorLeaders`/`sectorLaggards`
    (real day-over-day average % change per `Stock.sector`, computed
    here since no existing module measures sector performance).

Honest, named gaps (see EPIC-M1.139's Dependencies note): `marketStatus`
is always `MARKET_STATUS_UNKNOWN` (no market-calendar module exists to
know if the market is open -- M1.121, not even a stated dependency of
this EPIC); `indexes` is always `[]` (no index-level price feed is
ingested at all, only individual NSE equities).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DailyCandidateScan, MarketPrice, MarketRegime, Stock

from ..schemas.market import MARKET_STATUS_UNKNOWN, MarketSummary, SectorMove

SECTOR_LEADERBOARD_SIZE = 3


def _latest_regime(session: Session) -> MarketRegime | None:
    return session.scalar(
        select(MarketRegime).join(DailyCandidateScan, DailyCandidateScan.id == MarketRegime.scan_id).order_by(DailyCandidateScan.scan_date.desc()).limit(1)
    )


def _latest_two_price_dates(session: Session) -> tuple[datetime | None, datetime | None]:
    latest = session.scalar(select(func.max(MarketPrice.timestamp)))
    if latest is None:
        return None, None
    previous = session.scalar(select(func.max(MarketPrice.timestamp)).where(MarketPrice.timestamp < latest))
    return latest, previous


def _sector_moves(session: Session, latest: datetime, previous: datetime) -> list[SectorMove]:
    latest_prices = {
        stock_id: close
        for stock_id, close in session.execute(
            select(MarketPrice.stock_id, MarketPrice.close).where(MarketPrice.timestamp == latest)
        ).all()
    }
    previous_prices = {
        stock_id: close
        for stock_id, close in session.execute(
            select(MarketPrice.stock_id, MarketPrice.close).where(MarketPrice.timestamp == previous)
        ).all()
    }
    common_ids = set(latest_prices) & set(previous_prices)
    if not common_ids:
        return []

    sector_by_stock = dict(
        session.execute(select(Stock.id, Stock.sector).where(Stock.id.in_(common_ids))).all()
    )

    totals: dict[str, list[Decimal]] = {}
    for stock_id in common_ids:
        prev_price = previous_prices[stock_id]
        if prev_price == 0:
            continue
        change_pct = (latest_prices[stock_id] - prev_price) / prev_price * 100
        sector = sector_by_stock.get(stock_id) or "UNKNOWN"
        totals.setdefault(sector, []).append(change_pct)

    averages = [
        SectorMove(sector=sector, averageChangePct=sum(changes) / Decimal(len(changes)))
        for sector, changes in totals.items()
    ]
    return averages


def get_market_summary(session: Session) -> MarketSummary:
    regime = _latest_regime(session)
    latest_date, previous_date = _latest_two_price_dates(session)

    volume = None
    if latest_date is not None:
        volume = session.scalar(select(func.sum(MarketPrice.volume)).where(MarketPrice.timestamp == latest_date))

    sector_moves: list[SectorMove] = []
    if latest_date is not None and previous_date is not None:
        sector_moves = _sector_moves(session, latest_date, previous_date)
    sector_moves_sorted = sorted(sector_moves, key=lambda m: m.averageChangePct, reverse=True)

    return MarketSummary(
        asOf=latest_date if latest_date is not None else datetime.now(timezone.utc),
        marketStatus=MARKET_STATUS_UNKNOWN,
        regime=regime.regime if regime is not None else None,
        advanceDecline=regime.breadth_positive_ratio if regime is not None else None,
        volume=int(volume) if volume is not None else None,
        volatility=regime.average_atr_percent if regime is not None else None,
        indexes=[],
        sectorLeaders=sector_moves_sorted[:SECTOR_LEADERBOARD_SIZE],
        sectorLaggards=list(reversed(sector_moves_sorted[-SECTOR_LEADERBOARD_SIZE:])) if sector_moves_sorted else [],
    )
