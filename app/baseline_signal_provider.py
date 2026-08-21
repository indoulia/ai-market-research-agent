"""Deterministic technical baseline SignalProvider for operational discovery.

This is an executable baseline for M1.149 integration testing, not a trained
production model. It turns the existing persisted technical features into a
stable probability/confidence signal so the discovery pipeline can be exercised
without fabricating discovery records or bypassing the SignalProvider contract.
"""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from .scan import CandidateSignals

MODEL_VERSION = "baseline-technical-v1"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class TechnicalBaselineSignalProvider:
    """Deterministic, explainable baseline implementing the scan SignalProvider contract."""

    model_version = MODEL_VERSION

    def predict(self, stock_id: int, features: pd.Series) -> CandidateSignals:
        del stock_id  # Contract identity is intentionally not used by this baseline.

        trend = _clamp(0.5 + 4.0 * float(features["sma20_distance"]))
        volume = _clamp(float(features["volume_ratio_20d"]) / 2.0)
        volatility = _clamp(1.0 - float(features["atr_percent"]) / 0.10)

        probability = _clamp(0.55 * trend + 0.25 * volume + 0.20 * volatility)
        confidence = _clamp(
            0.40
            + 0.30 * _clamp(abs(float(features["sma20_distance"])) / 0.05)
            + 0.30 * _clamp(float(features["volume_ratio_20d"]) / 2.0)
        )

        return CandidateSignals(
            predicted_probability=Decimal(str(round(probability, 6))),
            confidence=Decimal(str(round(confidence, 6))),
        )
