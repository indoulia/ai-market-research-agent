"""EPIC-M1.10: deterministically select which of the platform's supported 1/3/5/7
trading-day horizons best fits a candidate, from evidence already available in the
repository (ATR% -- average true range as a percentage of price, from
app/features/technical.py), rather than a fixed default for every stock. The mapping
itself is a fixed, documented product/policy step function; it is NOT learned or
optimized from historical outcomes (that is a later calibration EPIC).
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from .consensus import ConsensusEvaluation
from .models import Prediction
from .recommendations import VALID_HORIZON_DAYS
from .consensus import record_qualifying_recommendation

SELECTION_VERSION = "PHS-001"

# Higher volatility (ATR% of price) means a positive move is expected to resolve
# sooner, so a shorter horizon is selected; lower volatility means a longer horizon is
# needed to accumulate the same move. Ordered highest-threshold-first; the first
# threshold atr_percent meets or exceeds wins. Below every threshold, the fallback
# (longest supported horizon) applies.
ATR_PERCENT_HORIZON_THRESHOLDS = (
    (Decimal("0.035"), 1),
    (Decimal("0.020"), 3),
    (Decimal("0.010"), 5),
)
FALLBACK_HORIZON_DAYS = 7

assert FALLBACK_HORIZON_DAYS in VALID_HORIZON_DAYS
assert all(horizon_days in VALID_HORIZON_DAYS for _, horizon_days in ATR_PERCENT_HORIZON_THRESHOLDS)
assert all(
    ATR_PERCENT_HORIZON_THRESHOLDS[i][0] > ATR_PERCENT_HORIZON_THRESHOLDS[i + 1][0]
    for i in range(len(ATR_PERCENT_HORIZON_THRESHOLDS) - 1)
), "thresholds must be strictly descending for the first-match-wins scan to be correct"


class InsufficientHorizonEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class HorizonSelection:
    horizon_days: int
    selection_version: str
    detail: str


def select_horizon(atr_percent: Decimal | None) -> HorizonSelection:
    """Deterministically select a supported horizon from ATR%. Missing evidence
    raises `InsufficientHorizonEvidenceError` explicitly rather than defaulting to a
    horizon; a negative ATR% (a data-quality impossibility) raises `ValueError`. Every
    return path is one of `VALID_HORIZON_DAYS` by construction (asserted above)."""
    if atr_percent is None:
        raise InsufficientHorizonEvidenceError("cannot select a horizon: atr_percent is missing")
    if atr_percent < 0:
        raise ValueError(f"atr_percent must be non-negative, got {atr_percent}")

    for threshold, horizon_days in ATR_PERCENT_HORIZON_THRESHOLDS:
        if atr_percent >= threshold:
            return HorizonSelection(
                horizon_days=horizon_days,
                selection_version=SELECTION_VERSION,
                detail=f"atr_percent={atr_percent} >= {threshold} -> horizon_days={horizon_days}",
            )

    return HorizonSelection(
        horizon_days=FALLBACK_HORIZON_DAYS,
        selection_version=SELECTION_VERSION,
        detail=f"atr_percent={atr_percent} below all thresholds -> horizon_days={FALLBACK_HORIZON_DAYS}",
    )


def record_recommendation_with_selected_horizon(
    session: Session,
    consensus_evaluation: ConsensusEvaluation,
    atr_percent: Decimal | None,
    **recommendation_kwargs,
) -> Prediction:
    """Select a horizon from `atr_percent`, then persist a positive recommendation
    (via the M1.8 consensus gate) with that horizon and the selection rule's version
    traced. Never issues a recommendation with an unselected/invalid horizon: horizon
    selection failures propagate before any persistence is attempted."""
    selection = select_horizon(atr_percent)
    return record_qualifying_recommendation(
        session,
        consensus_evaluation,
        horizon_days=selection.horizon_days,
        horizon_selection_version=selection.selection_version,
        **recommendation_kwargs,
    )
