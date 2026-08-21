"""EPIC-M1.124: measure the usefulness of one scan's opportunities not just
individually (M1.87's own composite ranking) but collectively -- surfacing
correlation, sector concentration and near-duplicate bets between
*simultaneously active* candidates, and applying a deterministic,
versioned concentration penalty to a diversified selection order without
ever touching the underlying prediction probabilities or M1.87's own
`PositiveOpportunityRanking` rows.

**Individual quality stays separately measurable (AC)**: this module
never recomputes or overwrites M1.87's `composite_score` -- it only reads
the scan's already-persisted `PositiveOpportunityRanking` rows (produced
by M1.99's `rank_scan_candidates`, itself a thin wrapper over M1.87) as
its `base_utility` input, then layers execution-cost/liquidity awareness
from M1.98's already-persisted `ExecutionCostAssessment` on top.

**Correlation between active and candidate opportunities**: computed from
real Pearson correlation of trailing daily returns already stored in
`MarketPrice` (no new data source, no fabricated correlation matrix) --
the same honest, deterministic posture other EPICs on this platform take
when a fuller factor-correlation model isn't available yet.

**Sector/concentration and near-duplicate detection**: sector
concentration is a plain count against `Stock.sector` (matching M1.59/
M1.109's existing use of the same field); a pair is flagged
"near-duplicate" when it is *both* same-sector *and* above the price-
correlation threshold -- two independent, weaker signals combined into
one stronger one, rather than either alone.

**Concentration penalty applied to ranking, without changing raw
probabilities (AC)**: `PortfolioUtilityAssessment` is a new, separate
table. `Prediction.predicted_probability`, `Prediction.opportunity_score`
and `PositiveOpportunityRanking` itself are never written to here.

**User preference constraints without contaminating global model
learning (AC)**: reuses M1.31's existing `UserPreference.preferred_sectors`
read-only; a sector outside a user's stated preference lowers that
user's *own* adjusted utility/exclusion, never `Prediction` or any
system-wide ranking field.

**Historical selection decisions remain reconstructable (AC)**:
`PortfolioUtilityAssessment` rows are immutable and idempotent by
`(prediction_id, evaluated_at)`, mirroring M1.87's own idempotency
convention; `measure_portfolio_selection_effectiveness` never mutates a
prior report, mirroring M1.99's `measure_ranking_effectiveness`.

**Honest gaps, not silent ones**: "liquidity" beyond M1.98's own
`liquidity_bucket` (true order-book microstructure) is M1.128's
not-yet-implemented domain; "benchmark-relative value" is M1.129's
domain and is not a declared dependency of this EPIC, so it is not read
here even though M1.129 has since merged -- a future EPIC's job to wire
in, not this one's to reach for opportunistically.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .execution_cost_model import get_execution_cost_assessment
from .models import (
    MarketPrice,
    PortfolioCorrelationReport,
    PortfolioSelectionEffectivenessReport,
    PortfolioUtilityAssessment,
    PositiveOpportunityRanking,
    Prediction,
    PredictionOutcome,
    RecommendationGeneration,
    ScanCandidate,
    Stock,
    UserPreference,
)
from .out_of_sample_validation import EvaluationWindow
from .recommendation_generator import OUTCOME_QUALIFIED
from .trust_report import MIN_SAMPLE_SIZE_FOR_COMPARISON, WEAKNESS_MARGIN

CORRELATION_RULE_VERSION = "PCR-001"
UTILITY_RULE_VERSION = "PUA-001"
EFFECTIVENESS_RULE_VERSION = "PSE-001"

# Fixed, documented policy constants -- not learned or fitted.
DEFAULT_LOOKBACK_DAYS = 60
HIGH_CORRELATION_THRESHOLD = Decimal("0.70")
SECTOR_CONCENTRATION_PENALTY_THRESHOLD = Decimal("0.40")  # a sector holding >40% of a scan's candidates
CONCENTRATION_PENALTY_PER_EXCESS = Decimal("0.15")
CORRELATION_PENALTY_PER_PAIR = Decimal("0.10")
MAX_TOTAL_PENALTY = Decimal("0.60")
PREFERENCE_EXCLUSION_PENALTY = Decimal("1.00")

REASON_SECTOR_CONCENTRATION = "SECTOR_CONCENTRATION"
REASON_HIGH_CORRELATION = "HIGH_CORRELATION_CLUSTER"
REASON_NOT_PREFERRED_SECTOR = "NOT_PREFERRED_SECTOR"

VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
VERDICT_DIVERSIFIED_BETTER = "DIVERSIFIED_BETTER"
VERDICT_RAW_BETTER = "RAW_BETTER"
VERDICT_NO_SIGNIFICANT_DIFFERENCE = "NO_SIGNIFICANT_DIFFERENCE"


def _qualified_candidates_for_scan(session: Session, scan_id: int) -> list[tuple[int, int, str | None]]:
    """(prediction_id, stock_id, sector) for this scan's M1.9-qualified candidates."""
    rows = session.execute(
        select(Prediction.id, Stock.id, Stock.sector)
        .join(RecommendationGeneration, RecommendationGeneration.prediction_id == Prediction.id)
        .join(ScanCandidate, ScanCandidate.id == RecommendationGeneration.scan_candidate_id)
        .join(Stock, Stock.id == Prediction.stock_id)
        .where(ScanCandidate.scan_id == scan_id, RecommendationGeneration.outcome == OUTCOME_QUALIFIED)
        .order_by(Stock.symbol.asc())
    ).all()
    return [(prediction_id, stock_id, sector) for prediction_id, stock_id, sector in rows]


def _daily_returns(session: Session, stock_id: int, *, as_of: datetime, lookback_days: int) -> list[Decimal]:
    rows = list(
        session.scalars(
            select(MarketPrice.close)
            .where(MarketPrice.stock_id == stock_id, MarketPrice.timestamp <= as_of)
            .order_by(MarketPrice.timestamp.desc())
            .limit(lookback_days + 1)
        ).all()
    )
    rows = list(reversed(rows))
    if len(rows) < 2:
        return []
    return [(rows[i] - rows[i - 1]) / rows[i - 1] for i in range(1, len(rows)) if rows[i - 1] != 0]


def _pearson_correlation(a: list[Decimal], b: list[Decimal]) -> Decimal | None:
    n = min(len(a), len(b))
    if n < 5:
        return None
    a, b = a[-n:], b[-n:]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((x - mean_b) ** 2 for x in b)
    if var_a == 0 or var_b == 0:
        return None
    return cov / (var_a.sqrt() * var_b.sqrt())


def assess_portfolio_correlation(
    session: Session,
    scan_id: int,
    *,
    evaluated_at: datetime,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    correlation_threshold: Decimal = HIGH_CORRELATION_THRESHOLD,
) -> PortfolioCorrelationReport:
    """Idempotent by `(scan_id, evaluated_at)`: a prior report for this
    exact scan/timestamp is returned unchanged."""
    existing = session.scalar(
        select(PortfolioCorrelationReport).where(
            PortfolioCorrelationReport.scan_id == scan_id, PortfolioCorrelationReport.evaluated_at == evaluated_at
        )
    )
    if existing is not None:
        return existing

    candidates = _qualified_candidates_for_scan(session, scan_id)

    sector_counts: dict[str, int] = {}
    for _prediction_id, _stock_id, sector in candidates:
        key = sector or "UNKNOWN"
        sector_counts[key] = sector_counts.get(key, 0) + 1

    returns_by_stock = {
        stock_id: _daily_returns(session, stock_id, as_of=evaluated_at, lookback_days=lookback_days)
        for _prediction_id, stock_id, _sector in candidates
    }

    high_correlation_pairs: list[list] = []
    near_duplicate_stock_ids: set[int] = set()
    sector_by_stock = {stock_id: sector for _prediction_id, stock_id, sector in candidates}
    stock_ids = [stock_id for _prediction_id, stock_id, _sector in candidates]

    for stock_a, stock_b in combinations(stock_ids, 2):
        correlation = _pearson_correlation(returns_by_stock[stock_a], returns_by_stock[stock_b])
        if correlation is None or correlation < correlation_threshold:
            continue
        high_correlation_pairs.append([stock_a, stock_b, str(correlation)])
        if sector_by_stock[stock_a] == sector_by_stock[stock_b] and sector_by_stock[stock_a] is not None:
            near_duplicate_stock_ids.add(stock_a)
            near_duplicate_stock_ids.add(stock_b)

    report = PortfolioCorrelationReport(
        scan_id=scan_id,
        candidate_count=len(candidates),
        lookback_days=lookback_days,
        sector_concentration=sector_counts,
        high_correlation_pairs=high_correlation_pairs,
        near_duplicate_stock_ids=sorted(near_duplicate_stock_ids),
        evaluated_at=evaluated_at,
        correlation_rule_version=CORRELATION_RULE_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _base_utility(session: Session, prediction_id: int, ranking: PositiveOpportunityRanking) -> Decimal | None:
    if ranking.composite_score is None:
        return None
    cost_assessment = get_execution_cost_assessment(session, prediction_id)
    if cost_assessment is None or cost_assessment.net_return is None or cost_assessment.gross_return in (None, Decimal("0")):
        return ranking.composite_score
    # Deterministic cost-awareness: scale the composite score by how much of
    # the gross return the execution cost model expects to survive, never
    # recomputing the composite score's own components.
    cost_efficiency = cost_assessment.net_return / cost_assessment.gross_return
    return ranking.composite_score * max(Decimal("0"), min(Decimal("1"), cost_efficiency))


def apply_portfolio_adjustment(
    session: Session,
    scan_id: int,
    *,
    evaluated_at: datetime,
    correlation_report: PortfolioCorrelationReport,
    user_id: str | None = None,
) -> tuple[PortfolioUtilityAssessment, ...]:
    """Idempotent by `(prediction_id, evaluated_at)`, matching M1.87's own
    convention. Never mutates `Prediction`, `PositiveOpportunityRanking`
    or any other system-wide field -- only ever writes new
    `PortfolioUtilityAssessment` rows."""
    existing = session.scalars(
        select(PortfolioUtilityAssessment).where(
            PortfolioUtilityAssessment.scan_id == scan_id, PortfolioUtilityAssessment.evaluated_at == evaluated_at
        )
    ).all()
    if existing:
        return tuple(existing)

    candidates = _qualified_candidates_for_scan(session, scan_id)
    rankings = {
        r.prediction_id: r
        for r in session.scalars(
            select(PositiveOpportunityRanking).where(
                PositiveOpportunityRanking.prediction_id.in_([p for p, _s, _sec in candidates]),
                PositiveOpportunityRanking.included.is_(True),
            )
        ).all()
    }

    preferred_sectors: set[str] | None = None
    if user_id is not None:
        preference = session.scalar(
            select(UserPreference)
            .where(UserPreference.user_id == user_id)
            .order_by(UserPreference.effective_at.desc())
        )
        if preference is not None and preference.preferred_sectors:
            preferred_sectors = set(preference.preferred_sectors)

    total_candidates = max(1, len(candidates))
    high_correlation_partners: dict[int, int] = {}
    for stock_a, stock_b, _corr in correlation_report.high_correlation_pairs:
        high_correlation_partners[stock_a] = high_correlation_partners.get(stock_a, 0) + 1
        high_correlation_partners[stock_b] = high_correlation_partners.get(stock_b, 0) + 1

    rows: list[PortfolioUtilityAssessment] = []
    for prediction_id, stock_id, sector in candidates:
        ranking = rankings.get(prediction_id)
        base_utility = _base_utility(session, prediction_id, ranking) if ranking is not None else None

        reasons: list[str] = []
        concentration_penalty = Decimal("0")
        sector_key = sector or "UNKNOWN"
        sector_share = Decimal(correlation_report.sector_concentration.get(sector_key, 0)) / Decimal(total_candidates)
        if sector_share > SECTOR_CONCENTRATION_PENALTY_THRESHOLD:
            concentration_penalty = CONCENTRATION_PENALTY_PER_EXCESS
            reasons.append(REASON_SECTOR_CONCENTRATION)

        correlation_penalty = Decimal("0")
        if high_correlation_partners.get(stock_id, 0) > 0:
            correlation_penalty = CORRELATION_PENALTY_PER_PAIR * min(3, high_correlation_partners[stock_id])
            reasons.append(REASON_HIGH_CORRELATION)

        preference_penalty = Decimal("0")
        included = ranking.included if ranking is not None else False
        if preferred_sectors is not None and sector not in preferred_sectors:
            preference_penalty = PREFERENCE_EXCLUSION_PENALTY
            reasons.append(REASON_NOT_PREFERRED_SECTOR)
            included = False

        total_penalty = min(MAX_TOTAL_PENALTY, concentration_penalty + correlation_penalty) + preference_penalty
        adjusted_utility = None if base_utility is None else max(Decimal("0"), base_utility * (Decimal("1") - min(Decimal("1"), total_penalty)))

        row = PortfolioUtilityAssessment(
            prediction_id=prediction_id,
            scan_id=scan_id,
            sector=sector,
            base_utility=base_utility,
            concentration_penalty=concentration_penalty,
            correlation_penalty=correlation_penalty,
            preference_penalty=preference_penalty,
            adjusted_utility=adjusted_utility,
            included=included,
            penalty_reasons=reasons,
            evaluated_at=evaluated_at,
            utility_rule_version=UTILITY_RULE_VERSION,
        )
        session.add(row)
        rows.append(row)

    session.commit()
    for row in rows:
        session.refresh(row)
    return tuple(rows)


def get_utility_history(session: Session, prediction_id: int) -> tuple[PortfolioUtilityAssessment, ...]:
    return tuple(
        session.scalars(
            select(PortfolioUtilityAssessment)
            .where(PortfolioUtilityAssessment.prediction_id == prediction_id)
            .order_by(PortfolioUtilityAssessment.id.asc())
        ).all()
    )


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _top_k_outcomes_by_field(session: Session, *, window: EvaluationWindow, top_k: int, order_desc_field, evaluated_at_field) -> list[str]:
    ranked_ids = session.execute(
        select(PortfolioUtilityAssessment.prediction_id)
        .where(PortfolioUtilityAssessment.included.is_(True), PortfolioUtilityAssessment.adjusted_utility.is_not(None))
        .order_by(order_desc_field.desc())
    ).scalars().all()
    top_ids = list(ranked_ids)[:top_k] if top_k else []
    if not top_ids:
        return []
    query = select(PredictionOutcome.outcome).where(
        PredictionOutcome.prediction_id.in_(top_ids), PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE"))
    )
    return list(session.scalars(query).all())


def measure_portfolio_selection_effectiveness(
    session: Session, *, window: EvaluationWindow, top_k: int, computed_at: datetime
) -> PortfolioSelectionEffectivenessReport:
    """Compares the realized success rate of this EPIC's diversified,
    penalty-adjusted top-K selection against M1.87's raw composite-ranked
    top-K, over the same already-resolved `PredictionOutcome` evidence --
    mirrors M1.99's `measure_ranking_effectiveness` comparison pattern.
    Below `MIN_SAMPLE_SIZE_FOR_COMPARISON` on either side, the report is
    honestly `INSUFFICIENT_SAMPLE`."""
    diversified_query = (
        select(PredictionOutcome.outcome)
        .join(PortfolioUtilityAssessment, PortfolioUtilityAssessment.prediction_id == PredictionOutcome.prediction_id)
        .where(
            PortfolioUtilityAssessment.included.is_(True),
            PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")),
        )
        .order_by(PortfolioUtilityAssessment.adjusted_utility.desc())
        .limit(top_k)
    )
    raw_query = (
        select(PredictionOutcome.outcome)
        .join(PositiveOpportunityRanking, PositiveOpportunityRanking.prediction_id == PredictionOutcome.prediction_id)
        .where(
            PositiveOpportunityRanking.included.is_(True),
            PositiveOpportunityRanking.rank_position <= top_k,
            PredictionOutcome.outcome.in_(("SUCCESS", "FAILURE")),
        )
    )
    if window.start is not None:
        diversified_query = diversified_query.where(PortfolioUtilityAssessment.evaluated_at >= window.start)
        raw_query = raw_query.where(PositiveOpportunityRanking.evaluated_at >= window.start)
    if window.end is not None:
        diversified_query = diversified_query.where(PortfolioUtilityAssessment.evaluated_at <= window.end)
        raw_query = raw_query.where(PositiveOpportunityRanking.evaluated_at <= window.end)

    diversified_outcomes = list(session.scalars(diversified_query).all())
    raw_outcomes = list(session.scalars(raw_query).all())

    diversified_sample_count = len(diversified_outcomes)
    raw_sample_count = len(raw_outcomes)
    diversified_success_count = sum(1 for o in diversified_outcomes if o == "SUCCESS")
    raw_success_count = sum(1 for o in raw_outcomes if o == "SUCCESS")
    diversified_success_rate = _rate(diversified_success_count, diversified_sample_count)
    raw_success_rate = _rate(raw_success_count, raw_sample_count)

    if diversified_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON or raw_sample_count < MIN_SAMPLE_SIZE_FOR_COMPARISON:
        verdict = VERDICT_INSUFFICIENT_SAMPLE
        success_rate_delta = None
    else:
        success_rate_delta = diversified_success_rate - raw_success_rate
        if success_rate_delta >= WEAKNESS_MARGIN:
            verdict = VERDICT_DIVERSIFIED_BETTER
        elif success_rate_delta <= -WEAKNESS_MARGIN:
            verdict = VERDICT_RAW_BETTER
        else:
            verdict = VERDICT_NO_SIGNIFICANT_DIFFERENCE

    report = PortfolioSelectionEffectivenessReport(
        window_label=window.label,
        top_k=top_k,
        diversified_sample_count=diversified_sample_count,
        diversified_success_count=diversified_success_count,
        diversified_success_rate=diversified_success_rate,
        raw_sample_count=raw_sample_count,
        raw_success_count=raw_success_count,
        raw_success_rate=raw_success_rate,
        success_rate_delta=success_rate_delta,
        verdict=verdict,
        computed_at=computed_at,
        effectiveness_rule_version=EFFECTIVENESS_RULE_VERSION,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_effectiveness_report_history(session: Session) -> tuple[PortfolioSelectionEffectivenessReport, ...]:
    return tuple(
        session.scalars(select(PortfolioSelectionEffectivenessReport).order_by(PortfolioSelectionEffectivenessReport.id.asc())).all()
    )
