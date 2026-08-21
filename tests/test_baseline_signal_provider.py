from decimal import Decimal

import pandas as pd

from app.baseline_signal_provider import MODEL_VERSION, TechnicalBaselineSignalProvider


def test_baseline_signal_provider_is_deterministic_and_bounded():
    provider = TechnicalBaselineSignalProvider()
    features = pd.Series(
        {
            "sma20_distance": 0.02,
            "volume_ratio_20d": 1.4,
            "atr_percent": 0.03,
        }
    )

    first = provider.predict(1, features)
    second = provider.predict(1, features)

    assert provider.model_version == MODEL_VERSION
    assert first == second
    assert Decimal("0") <= first.predicted_probability <= Decimal("1")
    assert Decimal("0") <= first.confidence <= Decimal("1")


def test_baseline_signal_provider_does_not_depend_on_stock_identity():
    provider = TechnicalBaselineSignalProvider()
    features = pd.Series(
        {
            "sma20_distance": 0.01,
            "volume_ratio_20d": 1.0,
            "atr_percent": 0.04,
        }
    )

    assert provider.predict(1, features) == provider.predict(999, features)
