"""Best-effort, "latest available" context lookups shared by the
recommendations list (M1.135) and detail/history (M1.137) endpoints.

Every function here is explicitly NOT a point-in-time-audited evidence
snapshot -- it is the single latest record available right now, and
returns ``None`` (never fabricates) when nothing exists yet.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CorporateAction, FundamentalDataRecord, MarketPrice, MarketRegime, NewsEventRecord, RecommendationEvidenceItem

EVIDENCE_FRESH = "FRESH"
EVIDENCE_STALE = "STALE"
EVIDENCE_UNKNOWN = "UNKNOWN"


def latest_market_price_pair(session: Session, stock_id: int) -> tuple[Decimal | None, Decimal | None]:
    rows = session.execute(
        select(MarketPrice.close)
        .where(MarketPrice.stock_id == stock_id)
        .order_by(MarketPrice.timestamp.desc())
        .limit(2)
    ).scalars().all()
    if not rows:
        return None, None
    price = rows[0]
    if len(rows) < 2 or rows[1] == 0:
        return price, None
    change_pct = (price - rows[1]) / rows[1] * 100
    return price, change_pct


def latest_market_price_pairs(
    session: Session, stock_ids: list[int]
) -> dict[int, tuple[Decimal | None, Decimal | None]]:
    """Batched form of `latest_market_price_pair` for a page of stock ids -- one query
    instead of one-per-row, using the same "latest two closes" definition."""
    if not stock_ids:
        return {}

    ranked = (
        select(
            MarketPrice.stock_id,
            MarketPrice.close,
            func.row_number()
            .over(partition_by=MarketPrice.stock_id, order_by=MarketPrice.timestamp.desc())
            .label("rn"),
        )
        .where(MarketPrice.stock_id.in_(stock_ids))
        .subquery()
    )
    rows = session.execute(
        select(ranked.c.stock_id, ranked.c.close).where(ranked.c.rn <= 2).order_by(ranked.c.stock_id, ranked.c.rn)
    ).all()

    closes_by_stock: dict[int, list[Decimal]] = {}
    for stock_id, close in rows:
        closes_by_stock.setdefault(stock_id, []).append(close)

    result: dict[int, tuple[Decimal | None, Decimal | None]] = {}
    for stock_id in stock_ids:
        closes = closes_by_stock.get(stock_id, [])
        if not closes:
            result[stock_id] = (None, None)
        elif len(closes) < 2 or closes[1] == 0:
            result[stock_id] = (closes[0], None)
        else:
            result[stock_id] = (closes[0], (closes[0] - closes[1]) / closes[1] * 100)
    return result


def fundamental_summary(session: Session, stock_id: int) -> str | None:
    record = session.scalar(
        select(FundamentalDataRecord)
        .where(FundamentalDataRecord.stock_id == stock_id)
        .order_by(FundamentalDataRecord.published_at.desc())
        .limit(1)
    )
    if record is None:
        return None
    parts = []
    if record.pe_ratio is not None:
        parts.append(f"P/E {record.pe_ratio}")
    if record.eps is not None:
        parts.append(f"EPS {record.eps}")
    if record.debt_to_equity is not None:
        parts.append(f"D/E {record.debt_to_equity}")
    return ", ".join(parts) if parts else None


def news_summary(session: Session, stock_id: int) -> str | None:
    record = session.scalar(
        select(NewsEventRecord)
        .where(NewsEventRecord.stock_id == stock_id)
        .order_by(NewsEventRecord.published_at.desc())
        .limit(1)
    )
    return record.headline if record is not None else None


def event_summary(session: Session, stock_id: int) -> str | None:
    record = session.scalar(
        select(CorporateAction)
        .where(CorporateAction.stock_id == stock_id)
        .order_by(CorporateAction.effective_date.desc())
        .limit(1)
    )
    if record is None:
        return None
    return f"{record.action_type} effective {record.effective_date.isoformat()}"


def market_summary(session: Session, scan_id: int | None) -> str | None:
    if scan_id is None:
        return None
    regime = session.scalar(select(MarketRegime).where(MarketRegime.scan_id == scan_id))
    return f"Market regime: {regime.regime}" if regime is not None else None


def evidence_freshness(session: Session, prediction_id: int) -> str:
    items = session.execute(
        select(RecommendationEvidenceItem.is_stale).where(RecommendationEvidenceItem.prediction_id == prediction_id)
    ).scalars().all()
    if not items:
        return EVIDENCE_UNKNOWN
    return EVIDENCE_STALE if any(items) else EVIDENCE_FRESH
