"""EPIC-M1.98: measure prediction usefulness using economically realistic
entry/exit cost assumptions rather than idealized prices -- a purely
advisory, read-only measurement layer that never executes, simulates
order routing for, or otherwise touches a real trade (scope: "keep
recommendation output advisory; do not execute trades").

Composes rather than duplicates: `outcome.actual_return` (M1.5/M1.95/
M1.96, already corporate-action-adjusted) is the one, unmodified GROSS
number this module ever reads -- it is never rewritten, and this module
adds no new logic to `app.outcomes`. Liquidity is assessed via `app.
discovery_segmentation.classify_liquidity_bucket` over the same
`volume_ratio_20d` M1.8's own consensus gate already uses as its
liquidity floor, reached through the prediction's `RecommendationGeneration`
link (the same provenance chain M1.97 already established as the mark of
a genuine, platform-produced prediction).

**The cost constants below are a fixed, documented, versioned
assumption -- not live regulatory or market-microstructure data.** This
platform ingests no real bid-ask spread, order-book depth, or brokerage/
exchange fee schedule; fabricating precise numbers this platform cannot
observe would be dishonest. `EXECUTION_COST_MODEL_VERSION` exists
precisely so a future EPIC that *does* have access to real cost data can
supersede these assumptions without ever being confused with them (AC:
"execution assumptions are versioned").

**Circuit limits are an explicitly named, out-of-scope gap, not a
fabricated detection**: correctly identifying a circuit-limit freeze
requires the exchange's own circuit-band data, which this platform does
not ingest anywhere. `UNAVAILABLE_EXECUTION_PRICE` covers the one real
signal this platform already has for "the recorded price cannot be
trusted as an execution basis" -- M1.5's own `outcome == "UNEVALUABLE"`
(invalid OHLC data) -- and is honestly silent on circuit limits rather
than inventing a check for data this platform doesn't have.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from .discovery_segmentation import BUCKET_UNCLASSIFIED, classify_liquidity_bucket
from .models import ExecutionCostAssessment, Prediction, PredictionOutcome, RecommendationGeneration, ScanCandidate

EXECUTION_COST_MODEL_VERSION = "ECM-001"

EXECUTABILITY_EXECUTABLE = "EXECUTABLE"
EXECUTABILITY_ILLIQUID = "ILLIQUID"
EXECUTABILITY_UNAVAILABLE = "UNAVAILABLE_EXECUTION_PRICE"

_UNEVALUABLE_OUTCOME = "UNEVALUABLE"

# Honest reachability note: M1.8's own consensus gate already requires
# `volume_ratio_20d >= MIN_VOLUME_RATIO_20D (0.75)` before a Prediction can
# exist at all -- exactly the NORMAL/LOW boundary -- so a genuine,
# platform-produced Prediction can never actually carry a LOW liquidity
# bucket today. EXECUTABILITY_ILLIQUID is kept anyway, the same
# forward-compatible posture M1.75 held for its never-yet-produced day-2
# horizon: a future change to the consensus threshold, a historical
# replay over data predating it, or a directly-constructed backtest row
# could still reach it, and this module should not need to change to
# handle that day.

# Fixed, documented, versioned assumptions (see module docstring) --
# expressed in basis points (1 bps = 0.01%), applied as one combined
# round-trip (entry + exit) cost, since this platform has no intraday
# data to honestly separate an entry-leg cost from an exit-leg cost.
BASE_SPREAD_COST_BPS = Decimal("10")
BASE_TRANSACTION_COST_BPS = Decimal("15")
LOW_LIQUIDITY_SLIPPAGE_SURCHARGE_BPS = Decimal("40")

DEFAULT_SENSITIVITY_MULTIPLIERS = (Decimal("0.5"), Decimal("1"), Decimal("1.5"), Decimal("2"))

IMMUTABLE_FIELDS = (
    "prediction_id",
    "gross_return",
    "liquidity_bucket",
    "executability_verdict",
    "estimated_cost_percent",
    "net_return",
    "cost_model_version",
    "assessed_at",
    "created_at",
)


class ExecutionCostAssessmentImmutableError(RuntimeError):
    pass


@event.listens_for(ExecutionCostAssessment, "before_update")
def _reject_immutable_field_changes(mapper, connection, target):
    state = inspect(target)
    changed = [f for f in IMMUTABLE_FIELDS if state.attrs[f].history.added or state.attrs[f].history.deleted]
    if changed:
        raise ExecutionCostAssessmentImmutableError(
            f"execution cost assessment {target.id} field(s) {changed} cannot be modified after creation"
        )


@dataclass(frozen=True)
class CostSensitivityPoint:
    cost_multiplier: Decimal
    net_return: Decimal


def _bps_to_fraction(bps: Decimal) -> Decimal:
    return bps / Decimal("10000")


def _linked_scan_candidate(session: Session, prediction_id: int) -> ScanCandidate | None:
    generation = session.scalar(
        select(RecommendationGeneration).where(RecommendationGeneration.prediction_id == prediction_id)
    )
    if generation is None:
        return None
    return session.get(ScanCandidate, generation.scan_candidate_id)


def assess_execution_cost(
    session: Session, prediction: Prediction, outcome: PredictionOutcome, *, assessed_at: datetime
) -> ExecutionCostAssessment:
    """Deterministic given `outcome`'s already-computed, immutable
    `actual_return` (AC: "historical outcomes remain reproducible") --
    never recomputes or overrides it. Idempotent by `prediction_id`."""
    existing = session.scalar(
        select(ExecutionCostAssessment).where(ExecutionCostAssessment.prediction_id == prediction.id)
    )
    if existing is not None:
        return existing

    gross_return = outcome.actual_return
    candidate = _linked_scan_candidate(session, prediction.id)
    liquidity_bucket = classify_liquidity_bucket(candidate.volume_ratio_20d if candidate is not None else None)

    if outcome.outcome == _UNEVALUABLE_OUTCOME or liquidity_bucket == BUCKET_UNCLASSIFIED:
        executability_verdict = EXECUTABILITY_UNAVAILABLE
        estimated_cost_percent = None
        net_return = None
    else:
        base_cost_bps = BASE_SPREAD_COST_BPS + BASE_TRANSACTION_COST_BPS
        if liquidity_bucket == "LOW":
            executability_verdict = EXECUTABILITY_ILLIQUID
            total_cost_bps = base_cost_bps + LOW_LIQUIDITY_SLIPPAGE_SURCHARGE_BPS
        else:
            executability_verdict = EXECUTABILITY_EXECUTABLE
            total_cost_bps = base_cost_bps
        estimated_cost_percent = _bps_to_fraction(total_cost_bps)
        net_return = gross_return - estimated_cost_percent

    assessment = ExecutionCostAssessment(
        prediction_id=prediction.id,
        gross_return=gross_return,
        liquidity_bucket=liquidity_bucket,
        executability_verdict=executability_verdict,
        estimated_cost_percent=estimated_cost_percent,
        net_return=net_return,
        cost_model_version=EXECUTION_COST_MODEL_VERSION,
        assessed_at=assessed_at,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def compute_cost_sensitivity(
    assessment: ExecutionCostAssessment, *, multipliers: tuple[Decimal, ...] = DEFAULT_SENSITIVITY_MULTIPLIERS
) -> tuple[CostSensitivityPoint, ...]:
    """"Add sensitivity analysis for execution assumptions" (scope): how
    `net_return` would look if the assumed cost were half, unchanged,
    1.5x, or double. Returns an empty tuple when the base cost itself is
    unavailable (`EXECUTABILITY_UNAVAILABLE`) -- there is no honest base
    to scale."""
    if assessment.estimated_cost_percent is None:
        return ()
    return tuple(
        CostSensitivityPoint(
            cost_multiplier=multiplier,
            net_return=assessment.gross_return - (assessment.estimated_cost_percent * multiplier),
        )
        for multiplier in multipliers
    )


def get_execution_cost_assessment(session: Session, prediction_id: int) -> ExecutionCostAssessment | None:
    return session.scalar(select(ExecutionCostAssessment).where(ExecutionCostAssessment.prediction_id == prediction_id))
