"""EPIC-M1.130: measure whether MRA's positive-only suppression decisions
are themselves correct -- segmented, so a platform-wide average cannot
hide a specific horizon/regime/sector/market-cap bucket where suppression
is quietly costing real opportunities or, just as importantly, correctly
avoiding real losses.

Reuses rather than recomputes: "preserve qualified-but-suppressed
candidates and reasons" is already M1.13's (`RecommendationGeneration`)
and M1.81's (`PositiveRecommendationGateDecision`) own job; "define
abstention outcomes for suppressed opportunities" is already M1.111's
own (`evaluate_recommendation` via `backfill_counterfactual_outcomes`,
applied uniformly to every qualified prediction regardless of selection).
This module's own, genuinely new contribution is **segmenting** M1.111's
already-aggregate published-vs-suppressed comparison
(`compare_published_vs_suppressed`) by the dimensions scope actually
names -- reusing M1.104's own segment vocabulary
(`SEGMENT_SECTOR`/`SEGMENT_MARKET_CAP`/`SEGMENT_HORIZON`) plus M1.26's
market regime (the same `classify_market_regime` on-demand call M1.85's
own `prediction_attribution` already makes from a report) -- the exact
same "aggregate report, computed and persisted fresh every call" posture
M1.85/M1.99/M1.102's own reports already established.

**Stock/setup-level and trust-level segmentation are honestly out of
scope for this first version** -- named here rather than fabricated,
the same restraint M1.109's own module already exercised for peer
valuation/fundamentals data it didn't yet have reliable coverage for.

Propose-only: no write path to `RecommendationGeneration`,
`RecommendationSelection`, `PositiveRecommendationGateDecision`, or any
ranking/Trust table -- "learn thresholds" and "feed validated abstention
evidence into ranking and Trust policy" (scope) remain a future
revision's job to compose, the same posture M1.101/M1.102/M1.104/M1.122's
own signals already established before being composed into anything.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .discovery_segmentation import classify_market_cap_bucket
from .market_regime import InsufficientRegimeEvidenceError, classify_market_regime
from .models import Prediction, PredictionOutcome, RecommendationGeneration, RecommendationSelection, ScanCandidate, SegmentAbstentionQualityReport, Stock
from .out_of_sample_validation import EvaluationWindow
from .recommendation_generator import OUTCOME_QUALIFIED
from .segment_calibration import GLOBAL_KEY, SEGMENT_GLOBAL, SEGMENT_HORIZON, SEGMENT_MARKET_CAP, SEGMENT_SECTOR
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, VERDICT_INSUFFICIENT_SAMPLE, VERDICT_OK, VERDICT_WEAK, WEAKNESS_MARGIN

ABSTENTION_QUALITY_VERSION = "AQR-001"

SEGMENT_REGIME = "REGIME"

# Fixed, documented order -- not a fallback chain like M1.104's (every
# level is reported independently here, none is "resolved" over another).
SEGMENT_LEVELS = (SEGMENT_SECTOR, SEGMENT_MARKET_CAP, SEGMENT_HORIZON, SEGMENT_REGIME, SEGMENT_GLOBAL)


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _regime_for_scan(session: Session, scan_id: int, cache: dict[int, str | None]) -> str | None:
    if scan_id not in cache:
        try:
            cache[scan_id] = classify_market_regime(session, scan_id).regime
        except InsufficientRegimeEvidenceError:
            cache[scan_id] = None
    return cache[scan_id]


def _segment_keys(session: Session, stock: Stock, horizon_days: int, scan_id: int, regime_cache: dict[int, str | None]) -> dict[str, str | None]:
    return {
        SEGMENT_SECTOR: stock.sector,
        SEGMENT_MARKET_CAP: classify_market_cap_bucket(stock.market_cap),
        SEGMENT_HORIZON: str(horizon_days),
        SEGMENT_REGIME: _regime_for_scan(session, scan_id, regime_cache),
        SEGMENT_GLOBAL: GLOBAL_KEY,
    }


def _qualified_rows(session: Session, window: EvaluationWindow):
    query = (
        select(PredictionOutcome, RecommendationSelection.selected, Prediction, Stock, ScanCandidate.scan_id)
        .select_from(RecommendationGeneration)
        .join(Prediction, Prediction.id == RecommendationGeneration.prediction_id)
        .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
        .join(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
        .join(Stock, Stock.id == Prediction.stock_id)
        .outerjoin(RecommendationSelection, RecommendationSelection.recommendation_generation_id == RecommendationGeneration.id)
        .where(RecommendationGeneration.outcome == OUTCOME_QUALIFIED, PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")))
    )
    if window.start is not None:
        query = query.where(Prediction.as_of_timestamp >= window.start)
    if window.end is not None:
        query = query.where(Prediction.as_of_timestamp <= window.end)
    return session.execute(query).all()


def _segment_stat(rows: list[tuple[PredictionOutcome, bool]]) -> dict:
    published = [o for o, selected in rows if selected]
    suppressed = [o for o, selected in rows if not selected]
    published_sample_count = len(published)
    suppressed_sample_count = len(suppressed)
    published_success_rate = _rate(sum(1 for o in published if o.outcome == "SUCCESS"), published_sample_count)
    suppressed_success_rate = _rate(sum(1 for o in suppressed if o.outcome == "SUCCESS"), suppressed_sample_count)
    opportunity_cost_total = sum((o.actual_return for o in suppressed if o.outcome == "SUCCESS"), Decimal("0"))
    avoided_loss_total = sum((abs(o.actual_return) for o in suppressed if o.outcome == "FAILURE"), Decimal("0"))
    published_loss_total = sum((abs(o.actual_return) for o in published if o.outcome == "FAILURE"), Decimal("0"))

    if (
        published_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or suppressed_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON
        or published_success_rate is None
        or suppressed_success_rate is None
    ):
        verdict = VERDICT_INSUFFICIENT_SAMPLE
        success_rate_delta = None
    else:
        success_rate_delta = published_success_rate - suppressed_success_rate
        verdict = VERDICT_OK if success_rate_delta >= WEAKNESS_MARGIN else VERDICT_WEAK

    return {
        "published_sample_count": published_sample_count,
        "suppressed_sample_count": suppressed_sample_count,
        "published_success_rate": str(published_success_rate) if published_success_rate is not None else None,
        "suppressed_success_rate": str(suppressed_success_rate) if suppressed_success_rate is not None else None,
        "success_rate_delta": str(success_rate_delta) if success_rate_delta is not None else None,
        "opportunity_cost_total": str(opportunity_cost_total),
        "avoided_loss_total": str(avoided_loss_total),
        "published_loss_total": str(published_loss_total),
        "verdict": verdict,
    }


def evaluate_segment_abstention_quality(
    session: Session, *, window: EvaluationWindow, computed_at: datetime
) -> SegmentAbstentionQualityReport:
    """Always computes and persists a fresh, independent report row (the
    same posture as M1.85/M1.99/M1.102's own reports)."""
    rows = _qualified_rows(session, window)
    sample_count = len(rows)

    regime_cache: dict[int, str | None] = {}
    grouped: dict[tuple[str, str], list[tuple[PredictionOutcome, bool]]] = {}
    for outcome, selected, prediction, stock, scan_id in rows:
        keys = _segment_keys(session, stock, prediction.horizon_days, scan_id, regime_cache)
        for level in SEGMENT_LEVELS:
            key = keys[level]
            if key is None:
                continue
            grouped.setdefault((level, key), []).append((outcome, bool(selected)))

    segment_breakdown = []
    any_measured = False
    for (level, key) in sorted(grouped):
        stat = _segment_stat(grouped[(level, key)])
        if stat["verdict"] != VERDICT_INSUFFICIENT_SAMPLE:
            any_measured = True
        segment_breakdown.append({"segment_level": level, "segment_key": key, **stat})

    report = SegmentAbstentionQualityReport(
        window_label=window.label,
        sample_count=sample_count,
        segment_breakdown=segment_breakdown,
        verdict=VERDICT_OK if any_measured else VERDICT_INSUFFICIENT_SAMPLE,
        computed_at=computed_at,
        report_rule_version=ABSTENTION_QUALITY_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_abstention_quality_report_history(session: Session) -> tuple[SegmentAbstentionQualityReport, ...]:
    return tuple(session.scalars(select(SegmentAbstentionQualityReport).order_by(SegmentAbstentionQualityReport.id.asc())).all())
