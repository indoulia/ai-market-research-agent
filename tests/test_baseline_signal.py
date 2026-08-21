"""EPIC-M1.149: BaselineSignalProvider is a fixed heuristic, not a trained
model -- these tests pin its determinism and its clamped output range rather
than any specific "accuracy"."""
from decimal import Decimal

import pandas as pd

from app.baseline_signal import BaselineSignalProvider


def _features(**overrides):
    base = {"sma20_distance": 0.0, "volume_ratio_20d": 1.0, "rsi_14": 50.0, "atr_percent": 0.02}
    base.update(overrides)
    return pd.Series(base)


def test_neutral_features_produce_neutral_probability():
    provider = BaselineSignalProvider()
    signals = provider.predict(1, _features())
    assert signals.predicted_probability == Decimal("0.5")


def test_same_inputs_always_produce_same_outputs():
    provider = BaselineSignalProvider()
    features = _features(sma20_distance=0.05, volume_ratio_20d=1.4, rsi_14=65.0)
    first = provider.predict(1, features)
    second = provider.predict(1, features)
    assert first == second


def test_positive_momentum_and_volume_raise_probability_above_neutral():
    provider = BaselineSignalProvider()
    signals = provider.predict(1, _features(sma20_distance=0.08, volume_ratio_20d=1.5, rsi_14=70.0))
    assert signals.predicted_probability > Decimal("0.5")


def test_negative_momentum_lowers_probability_below_neutral():
    provider = BaselineSignalProvider()
    signals = provider.predict(1, _features(sma20_distance=-0.08, volume_ratio_20d=0.5, rsi_14=30.0))
    assert signals.predicted_probability < Decimal("0.5")


def test_probability_and_confidence_never_reach_extremes():
    provider = BaselineSignalProvider()
    extreme = provider.predict(1, _features(sma20_distance=10.0, volume_ratio_20d=100.0, rsi_14=100.0, atr_percent=5.0))
    assert Decimal("0.05") <= extreme.predicted_probability <= Decimal("0.95")
    assert Decimal("0.20") <= extreme.confidence <= Decimal("0.90")


def test_missing_optional_features_default_to_neutral_not_error():
    provider = BaselineSignalProvider()
    signals = provider.predict(1, pd.Series({"sma20_distance": 0.02, "atr_percent": 0.01}))
    assert Decimal("0.05") <= signals.predicted_probability <= Decimal("0.95")


def test_model_version_is_tagged_as_baseline():
    assert BaselineSignalProvider().model_version == "BASELINE-001"
