import pandas as pd
import numpy as np

FEATURE_VERSION = "FV-001"

def add_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("timestamp").copy()
    out["return_1d"] = out["close"].pct_change(1)
    out["return_3d"] = out["close"].pct_change(3)
    out["return_5d"] = out["close"].pct_change(5)
    out["return_10d"] = out["close"].pct_change(10)
    out["return_20d"] = out["close"].pct_change(20)
    out["sma_20"] = out["close"].rolling(20).mean()
    out["sma_50"] = out["close"].rolling(50).mean()
    out["sma20_distance"] = out["close"] / out["sma_20"] - 1
    out["sma50_distance"] = out["close"] / out["sma_50"] - 1
    delta = out["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi_14"] = 100 - (100 / (1 + rs))
    out["volume_ma20"] = out["volume"].rolling(20).mean()
    out["volume_ratio_20d"] = out["volume"] / out["volume_ma20"]
    tr = pd.concat([
        out["high"] - out["low"],
        (out["high"] - out["close"].shift()).abs(),
        (out["low"] - out["close"].shift()).abs()
    ], axis=1).max(axis=1)
    out["atr_14"] = tr.rolling(14).mean()
    out["atr_percent"] = out["atr_14"] / out["close"]
    return out
