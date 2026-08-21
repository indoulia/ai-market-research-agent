"""EPIC-M1.87: rank the strongest positive opportunities from the pool of
candidates that already cleared M1.81's positive-only gate, combining
expected return, calibrated probability, M1.77 trust, M1.47 reward/risk,
M1.74 evidence quality and M1.83 stability into one deterministic,
explainable composite score -- then control concentration/duplicates so
one stock or sector cannot crowd out otherwise-stronger opportunities.

This module never manufactures a positive recommendation (Execution
Rule): it only ranks predictions whose *latest* `PositiveRecommendationGateDecision`
is already `VERDICT_GATE_PASS`. A prediction lacking a PASS verdict --
never gated at all, or suppressed -- is recorded with
`REASON_NOT_GATE_PASSED` and excluded, never silently dropped from the
snapshot.

Every raw signal is a read-only lookup into an existing module's latest
decision (never recomputed here); `composite_score` is the one new,
versioned number this module produces, from a fixed weighted-average
formula over whichever signals are available. `expected_return`/
`predicted_probability`/`trust`/`evidence_quality` are required (the gate
itself guarantees trust and evidence quality were computed; `Prediction`
guarantees the other two are never null) -- `reward_risk` (needs a
published M1.47 `RecommendationPublication`) and `stability` (needs a
computed M1.83 assessment) are optional and, when absent, the remaining
weights are renormalized rather than penalizing a candidate for a signal
nobody has computed yet.

A ranking run is keyed by `evaluated_at` as an immutable batch: once any
row exists for a given `evaluated_at`, that run's snapshot (including
excluded candidates) is the historical record and is never recomputed or
resorted (AC: "historical ranking decisions are reconstructable").
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .evidence_quality_gate import STATE_SUFFICIENT, get_quality_decision_history
from .models import Prediction, PositiveOpportunityRanking, PredictionTrustScore, Stock
from .positive_recommendation_gate import VERDICT_GATE_PASS, get_gate_decision_history
from .prediction_stability import STABILITY_VERDICT_STABLE, get_stability_history
from .prediction_trust_score import get_trust_score_history
from .target_stop_loss import get_publication

OPPORTUNITY_RANKING_VERSION = "OPR-001"

REASON_NOT_GATE_PASSED = "NOT_GATE_PASSED"
REASON_MISSING_TRUST_SCORE = "MISSING_TRUST_SCORE"
REASON_EVIDENCE_QUALITY_NOT_SUFFICIENT = "EVIDENCE_QUALITY_NOT_SUFFICIENT"
REASON_DUPLICATE_STOCK_LOWER_SCORE = "DUPLICATE_STOCK_LOWER_SCORE"
REASON_SECTOR_CONCENTRATION_LIMIT = "SECTOR_CONCENTRATION_LIMIT"

# Fixed, documented, versioned policy constants -- not learned or fitted.
# Weights sum to 1.00 across the four required components; when an
# optional component is available its weight is added to the pool and
# the whole set is renormalized by the available weight sum.
WEIGHT_EXPECTED_RETURN = Decimal("0.25")
WEIGHT_PROBABILITY = Decimal("0.20")
WEIGHT_TRUST = Decimal("0.25")
WEIGHT_EVIDENCE_QUALITY = Decimal("0.05")
WEIGHT_REWARD_RISK = Decimal("0.15")
WEIGHT_STABILITY = Decimal("0.10")

# Normalization caps: squash an unbounded raw signal into [0, 1] for the
# composite formula only -- the raw, un-normalized value is still what
# gets persisted in the corresponding `*_component` column.
EXPECTED_RETURN_NORMALIZATION_CAP = Decimal("0.20")

# Concentration control: at most one included opportunity per stock (the
# duplicate with the lower composite score is excluded), and at most
# this many included opportunities per sector.
MAX_INCLUDED_PER_SECTOR = 3


class PositiveOpportunityRankingImmutableError(RuntimeError):
    pass


IMMUTABLE_FIELDS = (
    "prediction_id",
    "stock_id",
    "horizon_days",
    "composite_score",
    "expected_return_component",
    "probability_component",
    "trust_component",
    "reward_risk_component",
    "evidence_quality_component",
    "stability_component",
    "rank_position",
    "included",
    "exclusion_reason",
    "evaluated_at",
    "ranking_rule_version",
    "created_at",
)


@event.listens_for(PositiveOpportunityRanking, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [
        field
        for field in IMMUTABLE_FIELDS
        if state.attrs[field].history.added or state.attrs[field].history.deleted
    ]
    if changed:
        raise PositiveOpportunityRankingImmutableError(
            f"positive opportunity ranking {target.id} field(s) {changed} cannot be modified after creation"
        )


def _is_gate_passed(session: Session, prediction_id: int) -> bool:
    history = get_gate_decision_history(session, prediction_id)
    if not history:
        return False
    return history[-1].verdict == VERDICT_GATE_PASS


def _trust_component(session: Session, prediction_id: int) -> Decimal | None:
    history = get_trust_score_history(session, prediction_id)
    if not history:
        return None
    return history[-1].overall_trust_score


def _evidence_quality_component(session: Session, prediction_id: int) -> Decimal | None:
    history = get_quality_decision_history(session, prediction_id)
    if not history:
        return None
    return Decimal("1") if history[-1].state == STATE_SUFFICIENT else Decimal("0")


def _reward_risk_component(session: Session, prediction_id: int) -> Decimal | None:
    publication = get_publication(session, prediction_id)
    if publication is None or not publication.published:
        return None
    return publication.reward_risk_ratio


def _stability_component(session: Session, prediction_id: int) -> Decimal | None:
    history = get_stability_history(session, prediction_id)
    if not history:
        return None
    return Decimal("1") if history[-1].stability_verdict == STABILITY_VERDICT_STABLE else Decimal("0")


def _normalize_expected_return(value: Decimal) -> Decimal:
    clamped = max(Decimal("0"), min(value, EXPECTED_RETURN_NORMALIZATION_CAP))
    return clamped / EXPECTED_RETURN_NORMALIZATION_CAP


def _normalize_reward_risk(value: Decimal) -> Decimal:
    clamped = max(Decimal("0"), value)
    return clamped / (clamped + Decimal("1"))


def _composite_score(
    *,
    expected_return: Decimal,
    probability: Decimal,
    trust: Decimal,
    evidence_quality: Decimal,
    reward_risk: Decimal | None,
    stability: Decimal | None,
) -> Decimal:
    weighted_sum = (
        WEIGHT_EXPECTED_RETURN * _normalize_expected_return(expected_return)
        + WEIGHT_PROBABILITY * probability
        + WEIGHT_TRUST * trust
        + WEIGHT_EVIDENCE_QUALITY * evidence_quality
    )
    available_weight = WEIGHT_EXPECTED_RETURN + WEIGHT_PROBABILITY + WEIGHT_TRUST + WEIGHT_EVIDENCE_QUALITY
    if reward_risk is not None:
        weighted_sum += WEIGHT_REWARD_RISK * _normalize_reward_risk(reward_risk)
        available_weight += WEIGHT_REWARD_RISK
    if stability is not None:
        weighted_sum += WEIGHT_STABILITY * stability
        available_weight += WEIGHT_STABILITY
    return weighted_sum / available_weight


def rank_positive_opportunities(
    session: Session,
    prediction_ids: Sequence[int],
    *,
    evaluated_at: datetime,
    horizon_days: int | None = None,
) -> tuple[PositiveOpportunityRanking, ...]:
    """Idempotent per `evaluated_at`: once any row exists for this
    timestamp, that batch's snapshot -- included and excluded alike -- is
    returned unchanged rather than resorted, regardless of a different
    `prediction_ids`/`horizon_days` passed on a later call (AC:
    "historical ranking decisions are reconstructable")."""
    existing = session.scalars(
        select(PositiveOpportunityRanking)
        .where(PositiveOpportunityRanking.evaluated_at == evaluated_at)
        .order_by(PositiveOpportunityRanking.id.asc())
    ).all()
    if existing:
        return tuple(existing)

    predictions = {
        p.id: p
        for p in session.scalars(select(Prediction).where(Prediction.id.in_(prediction_ids))).all()
    }
    stocks = {s.id: s for s in session.scalars(select(Stock).where(Stock.id.in_(p.stock_id for p in predictions.values()))).all()}

    rows: list[PositiveOpportunityRanking] = []
    scored: list[tuple[PositiveOpportunityRanking, Decimal]] = []

    for prediction_id in prediction_ids:
        prediction = predictions[prediction_id]
        if horizon_days is not None and prediction.horizon_days != horizon_days:
            continue

        if not _is_gate_passed(session, prediction_id):
            rows.append(PositiveOpportunityRanking(
                prediction_id=prediction_id, stock_id=prediction.stock_id, horizon_days=prediction.horizon_days,
                composite_score=None, expected_return_component=None, probability_component=None,
                trust_component=None, reward_risk_component=None, evidence_quality_component=None,
                stability_component=None, rank_position=None, included=False,
                exclusion_reason=REASON_NOT_GATE_PASSED, evaluated_at=evaluated_at,
                ranking_rule_version=OPPORTUNITY_RANKING_VERSION,
            ))
            continue

        trust = _trust_component(session, prediction_id)
        evidence_quality = _evidence_quality_component(session, prediction_id)
        reward_risk = _reward_risk_component(session, prediction_id)
        stability = _stability_component(session, prediction_id)

        if trust is None:
            reason = REASON_MISSING_TRUST_SCORE
        elif evidence_quality != Decimal("1"):
            reason = REASON_EVIDENCE_QUALITY_NOT_SUFFICIENT
        else:
            reason = None

        if reason is not None:
            rows.append(PositiveOpportunityRanking(
                prediction_id=prediction_id, stock_id=prediction.stock_id, horizon_days=prediction.horizon_days,
                composite_score=None, expected_return_component=prediction.target_return,
                probability_component=prediction.predicted_probability, trust_component=trust,
                reward_risk_component=reward_risk, evidence_quality_component=evidence_quality,
                stability_component=stability, rank_position=None, included=False, exclusion_reason=reason,
                evaluated_at=evaluated_at, ranking_rule_version=OPPORTUNITY_RANKING_VERSION,
            ))
            continue

        composite_score = _composite_score(
            expected_return=prediction.target_return, probability=prediction.predicted_probability,
            trust=trust, evidence_quality=evidence_quality, reward_risk=reward_risk, stability=stability,
        )
        row = PositiveOpportunityRanking(
            prediction_id=prediction_id, stock_id=prediction.stock_id, horizon_days=prediction.horizon_days,
            composite_score=composite_score, expected_return_component=prediction.target_return,
            probability_component=prediction.predicted_probability, trust_component=trust,
            reward_risk_component=reward_risk, evidence_quality_component=evidence_quality,
            stability_component=stability, rank_position=None, included=True, exclusion_reason=None,
            evaluated_at=evaluated_at, ranking_rule_version=OPPORTUNITY_RANKING_VERSION,
        )
        rows.append(row)
        scored.append((row, composite_score))

    # Concentration control: within each stock, keep only the highest-scoring
    # row; the rest of that stock's otherwise-eligible rows are excluded as
    # duplicates before sector concentration is even considered.
    scored.sort(key=lambda item: (-item[1], stocks[item[0].stock_id].symbol))
    best_score_per_stock: dict[int, PositiveOpportunityRanking] = {}
    for row, _score in scored:
        current_best = best_score_per_stock.get(row.stock_id)
        if current_best is None:
            best_score_per_stock[row.stock_id] = row
        else:
            row.included = False
            row.exclusion_reason = REASON_DUPLICATE_STOCK_LOWER_SCORE

    survivors = [row for row, _score in scored if row.included]

    sector_counts: dict[str | None, int] = {}
    for row in survivors:
        sector = stocks[row.stock_id].sector
        count = sector_counts.get(sector, 0)
        if count >= MAX_INCLUDED_PER_SECTOR:
            row.included = False
            row.exclusion_reason = REASON_SECTOR_CONCENTRATION_LIMIT
        else:
            sector_counts[sector] = count + 1

    final_included = [row for row in survivors if row.included]
    final_included.sort(key=lambda row: (-row.composite_score, stocks[row.stock_id].symbol))
    for position, row in enumerate(final_included, start=1):
        row.rank_position = position

    session.add_all(rows)
    session.commit()
    for row in rows:
        session.refresh(row)
    return tuple(rows)


def get_ranking_history(session: Session, prediction_id: int) -> tuple[PositiveOpportunityRanking, ...]:
    return tuple(
        session.scalars(
            select(PositiveOpportunityRanking)
            .where(PositiveOpportunityRanking.prediction_id == prediction_id)
            .order_by(PositiveOpportunityRanking.id.asc())
        ).all()
    )
