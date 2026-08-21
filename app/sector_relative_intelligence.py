"""EPIC-M1.109: evaluate a stock relative to its sector peers so a
positive opportunity reflects genuine relative strength, not merely
absolute movement the whole sector happens to be making together.

**Point-in-time peer membership** (scope) is preserved the same way
M1.34's `DiscoverySegment` already preserves sector/market-cap
classification for a discovery: the peer group actually considered
(`peer_stock_ids`) and every value derived from it are frozen into the
immutable assessment row at `evaluated_at` -- if `Stock.sector` is
reclassified later, this assessment's frozen peer list and z-score are
unaffected, exactly M1.34's own established posture.

**Relative momentum** is measured only from the exact same scan
snapshot the target prediction's own candidacy came from -- every peer's
`sma20_distance` is read from a `ScanCandidate` row in that same
`DailyCandidateScan`, never from a different day's data, so the
comparison is genuinely same-point-in-time, not just same-sector.

**Relative valuation/fundamentals and event impact are honestly out of
scope for this first version** -- this platform's fundamental data
(M1.72/M1.91) does not yet have guaranteed peer coverage on the same
date for a reliable cross-sectional comparison, and forcing one would
risk comparing stale, unevenly-aged data across peers. Named here
rather than fabricated, the same posture this platform's provider EPICs
already established for genuinely-missing capabilities.

Propose-only: no write path to `Prediction`, `PredictionTrustScore`, or
any ranking table -- "feed relative evidence into ranking and Trust
Score" (scope) remains a future revision's job.
"""
from __future__ import annotations

import statistics
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Prediction,
    PredictionOutcome,
    RecommendationGeneration,
    ScanCandidate,
    SectorPerformanceReport,
    SectorRelativeAssessment,
    Stock,
)
from .out_of_sample_validation import EvaluationWindow
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK, WEAKNESS_MARGIN

SECTOR_RELATIVE_VERSION = "SRI-001"

VERDICT_STRONGER_THAN_PEERS = "STRONGER_THAN_PEERS"
VERDICT_WEAKER_THAN_PEERS = "WEAKER_THAN_PEERS"
VERDICT_IN_LINE_WITH_PEERS = "IN_LINE_WITH_PEERS"
VERDICT_INSUFFICIENT_PEER_GROUP = "INSUFFICIENT_PEER_GROUP"

REPORT_VERDICT_MEASURED = "MEASURED"

# Fixed, documented, versioned policy constants -- not learned or fitted.
MIN_PEER_GROUP_SIZE = 3
RELATIVE_STRENGTH_ZSCORE_THRESHOLD = Decimal("0.5")


def _scan_candidate_for_prediction(session: Session, prediction: Prediction) -> ScanCandidate | None:
    generation = session.scalar(select(RecommendationGeneration).where(RecommendationGeneration.prediction_id == prediction.id))
    if generation is None:
        return None
    return session.get(ScanCandidate, generation.scan_candidate_id)


def assess_sector_relative_strength(
    session: Session, prediction: Prediction, *, evaluated_at: datetime
) -> SectorRelativeAssessment:
    """Idempotent by `(prediction_id, evaluated_at)`."""
    existing = session.scalar(
        select(SectorRelativeAssessment).where(
            SectorRelativeAssessment.prediction_id == prediction.id, SectorRelativeAssessment.evaluated_at == evaluated_at,
        )
    )
    if existing is not None:
        return existing

    stock = session.get(Stock, prediction.stock_id)
    candidate = _scan_candidate_for_prediction(session, prediction)
    target_momentum = candidate.sma20_distance if candidate is not None else None

    peer_rows: list[tuple[int, Decimal]] = []
    if candidate is not None and stock.sector is not None:
        peers = session.execute(
            select(ScanCandidate.stock_id, ScanCandidate.sma20_distance)
            .join(Stock, Stock.id == ScanCandidate.stock_id)
            .where(
                ScanCandidate.scan_id == candidate.scan_id, ScanCandidate.eligible.is_(True),
                ScanCandidate.stock_id != prediction.stock_id, Stock.sector == stock.sector,
                ScanCandidate.sma20_distance.isnot(None),
            )
        ).all()
        peer_rows = list(peers)

    peer_stock_ids = sorted({stock_id for stock_id, _momentum in peer_rows})
    peer_group_size = len(peer_stock_ids)

    if peer_group_size < MIN_PEER_GROUP_SIZE or target_momentum is None:
        verdict = VERDICT_INSUFFICIENT_PEER_GROUP
        peer_mean_momentum = None
        peer_momentum_stdev = None
        relative_momentum_zscore = None
    else:
        peer_momentum_values = [momentum for _stock_id, momentum in peer_rows]
        peer_mean_momentum = statistics.mean(peer_momentum_values)
        peer_momentum_stdev = statistics.pstdev(peer_momentum_values) if len(peer_momentum_values) > 1 else Decimal("0")
        if peer_momentum_stdev == 0:
            verdict = VERDICT_INSUFFICIENT_PEER_GROUP
            relative_momentum_zscore = None
        else:
            relative_momentum_zscore = (target_momentum - peer_mean_momentum) / peer_momentum_stdev
            if relative_momentum_zscore >= RELATIVE_STRENGTH_ZSCORE_THRESHOLD:
                verdict = VERDICT_STRONGER_THAN_PEERS
            elif relative_momentum_zscore <= -RELATIVE_STRENGTH_ZSCORE_THRESHOLD:
                verdict = VERDICT_WEAKER_THAN_PEERS
            else:
                verdict = VERDICT_IN_LINE_WITH_PEERS

    assessment = SectorRelativeAssessment(
        prediction_id=prediction.id, sector=stock.sector or "UNCLASSIFIED", peer_group_size=peer_group_size,
        peer_stock_ids=peer_stock_ids, target_momentum=target_momentum, peer_mean_momentum=peer_mean_momentum,
        peer_momentum_stdev=peer_momentum_stdev, relative_momentum_zscore=relative_momentum_zscore, verdict=verdict,
        evaluated_at=evaluated_at, assessment_rule_version=SECTOR_RELATIVE_VERSION,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def get_sector_relative_history(session: Session, prediction_id: int) -> tuple[SectorRelativeAssessment, ...]:
    return tuple(
        session.scalars(
            select(SectorRelativeAssessment).where(SectorRelativeAssessment.prediction_id == prediction_id).order_by(SectorRelativeAssessment.id.asc())
        ).all()
    )


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _outcomes_in_window(session: Session, window: EvaluationWindow, *, sector: str | None) -> list[str]:
    query = (
        select(PredictionOutcome.outcome)
        .select_from(PredictionOutcome)
        .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
        .join(Stock, Stock.id == Prediction.stock_id)
        .where(PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    )
    if sector is not None:
        query = query.where(Stock.sector == sector)
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    return list(session.scalars(query).all())


def compare_sector_performance(session: Session, *, sector: str, window: EvaluationWindow, computed_at: datetime) -> SectorPerformanceReport:
    """Always computes and persists a fresh, independent report row --
    the same "report" posture as M1.85/M1.99/M1.102/M1.108."""
    sector_outcomes = _outcomes_in_window(session, window, sector=sector)
    baseline_outcomes = _outcomes_in_window(session, window, sector=None)

    sector_sample_count = len(sector_outcomes)
    baseline_sample_count = len(baseline_outcomes)
    sector_success_rate = _rate(sum(1 for o in sector_outcomes if o == "SUCCESS"), sector_sample_count)
    baseline_success_rate = _rate(sum(1 for o in baseline_outcomes if o == "SUCCESS"), baseline_sample_count)

    if (
        sector_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or baseline_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or sector_success_rate is None
        or baseline_success_rate is None
    ):
        verdict = VERDICT_INSUFFICIENT_SAMPLE
    elif baseline_success_rate - sector_success_rate >= WEAKNESS_MARGIN:
        verdict = VERDICT_WEAK
    else:
        verdict = VERDICT_OK

    report = SectorPerformanceReport(
        sector=sector, window_label=window.label, sector_sample_count=sector_sample_count,
        sector_success_rate=sector_success_rate, baseline_sample_count=baseline_sample_count,
        baseline_success_rate=baseline_success_rate, verdict=verdict, computed_at=computed_at,
        report_rule_version=SECTOR_RELATIVE_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_sector_performance_history(session: Session, sector: str) -> tuple[SectorPerformanceReport, ...]:
    return tuple(
        session.scalars(
            select(SectorPerformanceReport).where(SectorPerformanceReport.sector == sector).order_by(SectorPerformanceReport.id.asc())
        ).all()
    )
