import pandas as pd
import numpy as np
from app.features.technical import add_basic_features

def test_features_are_point_in_time():
    n = 60
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="D"),
        "open": np.arange(100, 100+n, dtype=float),
        "high": np.arange(101, 101+n, dtype=float),
        "low": np.arange(99, 99+n, dtype=float),
        "close": np.arange(100, 100+n, dtype=float),
        "volume": np.full(n, 1000),
    })
    result = add_basic_features(df)
    assert "return_1d" in result
    assert "rsi_14" in result
    assert result.loc[30, "return_1d"] == df.loc[30, "close"] / df.loc[29, "close"] - 1
