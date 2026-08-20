"""EPIC-M1.12: scan the supported NSE universe once per trading day and produce a
deterministic candidate set for downstream evaluation (M1.13). Reuses the existing
feature pipeline (app/features/technical.py) against persisted market data
(app/models.py MarketPrice); the predicted probability/confidence signal is supplied
by an injected `SignalProvider` (mirrors the `DailyHistoryProvider` protocol in
app/market_data/ingest.py) so the scan stays deterministic and testable without a
trained model dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Protocol

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .features.technical import FEATURE_VERSION, add_basic_features
from .market_data.quality import NSE_TIMEZONE
from .models import DailyCandidateScan, MarketPrice, ScanCandidate, Stock

UNIVERSE_VERSION = "DCS-001"

REQUIRED_FEATURE_COLUMNS = ("sma20_distance", "volume_ratio_20d", "atr_percent")


@dataclass(frozen=True)
class CandidateSignals:
    predicted_probability: Decimal
    confidence: Decimal


class SignalProvider(Protocol):
    model_version: str

    def predict(self, stock_id: int, features: pd.Series) -> CandidateSignals: ...


@dataclass(frozen=True)
class ScanSummary:
    scan: DailyCandidateScan
    candidates: tuple[ScanCandidate, ...]


def run_daily_candidate_scan(
    session: Session,
    scan_date: date,
    signal_provider: SignalProvider,
    universe_version: str = UNIVERSE_VERSION,
) -> ScanSummary:
    """Scan every active stock for `scan_date`. Idempotent: re-running for the same
    (scan_date, universe_version) returns the already-persisted scan and its
    candidates rather than creating duplicates."""
    existing = session.scalar(
        select(DailyCandidateScan).where(
            DailyCandidateScan.scan_date == scan_date,
            DailyCandidateScan.universe_version == universe_version,
        )
    )
    if existing is not None:
        candidates = session.scalars(
            select(ScanCandidate)
            .where(ScanCandidate.scan_id == existing.id)
            .order_by(ScanCandidate.stock_id)
        ).all()
        return ScanSummary(scan=existing, candidates=tuple(candidates))

    scan = DailyCandidateScan(
        scan_date=scan_date,
        universe_version=universe_version,
        eligible_count=0,
        excluded_count=0,
    )
    session.add(scan)
    session.flush()

    cutoff = datetime.combine(scan_date, time.min, NSE_TIMEZONE)
    stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.symbol)).all()

    candidates: list[ScanCandidate] = []
    eligible_count = 0
    for stock in stocks:
        rows = session.scalars(
            select(MarketPrice)
            .where(MarketPrice.stock_id == stock.id, MarketPrice.timestamp <= cutoff)
            .order_by(MarketPrice.timestamp)
        ).all()
        candidate = _evaluate_stock(scan.id, stock.id, rows, scan_date, signal_provider)
        session.add(candidate)
        candidates.append(candidate)
        if candidate.eligible:
            eligible_count += 1

    scan.eligible_count = eligible_count
    scan.excluded_count = len(candidates) - eligible_count
    session.flush()
    session.commit()
    session.refresh(scan)
    return ScanSummary(scan=scan, candidates=tuple(candidates))


def _evaluate_stock(
    scan_id: int,
    stock_id: int,
    rows: list[MarketPrice],
    scan_date: date,
    signal_provider: SignalProvider,
) -> ScanCandidate:
    if not rows:
        return _excluded(scan_id, stock_id, "missing_market_data", data_quality_passed=None)

    latest_session = rows[-1].timestamp.astimezone(NSE_TIMEZONE).date()
    if latest_session < scan_date:
        return _excluded(scan_id, stock_id, "stale_market_data", data_quality_passed=False)

    frame = pd.DataFrame(
        [
            {
                "timestamp": row.timestamp,
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": row.volume,
            }
            for row in rows
        ]
    )
    features = add_basic_features(frame).iloc[-1]
    if any(pd.isna(features[column]) for column in REQUIRED_FEATURE_COLUMNS):
        return _excluded(scan_id, stock_id, "invalid_market_data", data_quality_passed=False)

    sma20_distance = Decimal(str(round(float(features["sma20_distance"]), 6)))
    volume_ratio_20d = Decimal(str(round(float(features["volume_ratio_20d"]), 6)))
    atr_percent = Decimal(str(round(float(features["atr_percent"]), 6)))
    signals = signal_provider.predict(stock_id, features)

    return ScanCandidate(
        scan_id=scan_id,
        stock_id=stock_id,
        eligible=True,
        exclusion_reason=None,
        predicted_probability=signals.predicted_probability,
        confidence=signals.confidence,
        sma20_distance=sma20_distance,
        volume_ratio_20d=volume_ratio_20d,
        atr_percent=atr_percent,
        data_quality_passed=True,
        model_version=signal_provider.model_version,
        feature_version=FEATURE_VERSION,
    )


def _excluded(scan_id: int, stock_id: int, reason: str, *, data_quality_passed: bool | None) -> ScanCandidate:
    return ScanCandidate(
        scan_id=scan_id,
        stock_id=stock_id,
        eligible=False,
        exclusion_reason=reason,
        data_quality_passed=data_quality_passed,
    )
