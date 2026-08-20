"""EPIC-M1.26: classify the market environment for one daily candidate scan
(M1.12) from the breadth (fraction of eligible candidates in a positive
trend) and average volatility (ATR%) already computed by that scan's
`ScanCandidate` rows -- so recommendation performance can later be measured
by regime and future scoring can use regime-aware evidence.

This repo has no market-wide index data source (e.g. NIFTY 50), so "market
regime" is defined here as an aggregate over the platform's own scanned
universe on a given day -- breadth (what fraction of eligible stocks are
trending up) and average volatility -- rather than a single external index.
Since `ScanCandidate.sma20_distance`/`atr_percent` are themselves already
computed only from `MarketPrice` rows up to the scan's cutoff (M1.12's own
point-in-time safety), regime classification inherits "no future data is
used" for free -- no new leakage risk is introduced here.

`_classify` is a pure function (breadth ratio, average ATR% -> regime label)
so it can be reused unchanged by a historical-replay caller (M1.24) computing
regime from replayed, not-yet-persisted point-in-time candidates -- this
module doesn't itself modify `app/historical_replay.py`.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import MarketRegime, ScanCandidate

REGIME_RULE_VERSION = "REG-001"

# Fixed, documented, versioned policy constants -- a deterministic step
# function, not learned or optimized from outcomes.
BULLISH_BREADTH_THRESHOLD = Decimal("0.60")
BEARISH_BREADTH_THRESHOLD = Decimal("0.40")
HIGH_VOLATILITY_ATR_THRESHOLD = Decimal("0.03")

TREND_BULLISH = "BULLISH"
TREND_BEARISH = "BEARISH"
TREND_NEUTRAL = "NEUTRAL"

VOLATILITY_HIGH = "HIGH_VOL"
VOLATILITY_LOW = "LOW_VOL"


class InsufficientRegimeEvidenceError(RuntimeError):
    """Raised when a scan has no eligible candidates at all -- there is no
    breadth to compute, so no regime is fabricated (AC: "every recommendation
    can be associated with a regime *when sufficient data exists*")."""


def _classify(breadth_positive_ratio: Decimal, average_atr_percent: Decimal | None) -> str:
    if breadth_positive_ratio >= BULLISH_BREADTH_THRESHOLD:
        trend = TREND_BULLISH
    elif breadth_positive_ratio <= BEARISH_BREADTH_THRESHOLD:
        trend = TREND_BEARISH
    else:
        trend = TREND_NEUTRAL

    if average_atr_percent is None:
        return trend

    volatility = VOLATILITY_HIGH if average_atr_percent >= HIGH_VOLATILITY_ATR_THRESHOLD else VOLATILITY_LOW
    return f"{trend}_{volatility}"


def classify_market_regime(session: Session, scan_id: int) -> MarketRegime:
    """Idempotent by `scan_id` uniqueness: re-classifying an already
    classified scan returns the original row unchanged rather than
    re-deriving it (reproducibility, AC: "regime classification is
    reproducible for the same inputs" -- the first classification is the
    historical record, exactly like this platform's other scan-scoped
    idempotent functions, e.g. M1.14's `select_recommendations_for_scan`)."""
    existing = session.scalar(select(MarketRegime).where(MarketRegime.scan_id == scan_id))
    if existing is not None:
        return existing

    candidates = session.scalars(
        select(ScanCandidate).where(ScanCandidate.scan_id == scan_id, ScanCandidate.eligible.is_(True))
    ).all()
    if not candidates:
        raise InsufficientRegimeEvidenceError(f"scan {scan_id} has no eligible candidates; cannot classify a regime")

    positive_count = sum(1 for c in candidates if c.sma20_distance is not None and c.sma20_distance > 0)
    breadth_positive_ratio = Decimal(positive_count) / Decimal(len(candidates))

    atr_values = [c.atr_percent for c in candidates if c.atr_percent is not None]
    average_atr_percent = sum(atr_values, Decimal("0")) / Decimal(len(atr_values)) if atr_values else None

    regime = MarketRegime(
        scan_id=scan_id,
        regime=_classify(breadth_positive_ratio, average_atr_percent),
        breadth_positive_ratio=breadth_positive_ratio,
        average_atr_percent=average_atr_percent,
        eligible_count=len(candidates),
        regime_rule_version=REGIME_RULE_VERSION,
    )
    session.add(regime)
    session.commit()
    session.refresh(regime)
    return regime
