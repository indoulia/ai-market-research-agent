"""EPIC-M1.149: deterministic SignalProvider used by the discovery scan when no
real model is wired yet. Every input is an engineered technical feature already
computed by `app/scan.py` (via `add_basic_features`) -- this never fetches its
own data or calls an external model. Documented clearly so BASELINE-001 is never
mistaken for a trained/predictive model: it is a fixed, auditable heuristic over
momentum/volume/RSI, deliberately clamped away from 0/1 so it never claims
certainty a heuristic hasn't earned.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from .scan import CandidateSignals

MODEL_VERSION = "BASELINE-001"

_PROBABILITY_FLOOR = 0.05
_PROBABILITY_CEILING = 0.95
_CONFIDENCE_FLOOR = 0.20
_CONFIDENCE_CEILING = 0.90


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe(features: pd.Series, column: str, default: float = 0.0) -> float:
    value = features.get(column)
    return default if value is None or pd.isna(value) else float(value)


@dataclass(frozen=True)
class BaselineSignalProvider:
    """Fixed heuristic over momentum (`sma20_distance`), volume surge
    (`volume_ratio_20d`) and RSI (`rsi_14`) -- the first two are already
    required by `app/scan.py`'s own feature-quality gate, so this introduces no
    new data requirement. Not a trained model: identical inputs always produce
    identical outputs, and both outputs stay clamped away from 0/1."""

    model_version: str = MODEL_VERSION

    def predict(self, stock_id: int, features: pd.Series) -> CandidateSignals:
        momentum = _clip(_safe(features, "sma20_distance") / 0.10, -1.0, 1.0)
        volume_signal = _clip(_safe(features, "volume_ratio_20d", default=1.0) - 1.0, -1.0, 1.0)
        rsi_signal = _clip((_safe(features, "rsi_14", default=50.0) - 50.0) / 50.0, -1.0, 1.0)
        composite = (momentum + volume_signal + rsi_signal) / 3.0
        probability = _clip(0.5 + 0.25 * composite, _PROBABILITY_FLOOR, _PROBABILITY_CEILING)

        atr_percent = _safe(features, "atr_percent")
        confidence = _clip(1.0 - min(atr_percent * 5.0, 0.6), _CONFIDENCE_FLOOR, _CONFIDENCE_CEILING)

        return CandidateSignals(
            predicted_probability=Decimal(str(round(probability, 6))),
            confidence=Decimal(str(round(confidence, 6))),
        )
