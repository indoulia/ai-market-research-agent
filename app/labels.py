import pandas as pd

def add_forward_labels(df: pd.DataFrame, horizons=(1, 3, 5, 7), target_return=0.02) -> pd.DataFrame:
    out = df.sort_values("timestamp").copy()
    for h in horizons:
        future_close = out["close"].shift(-h)
        out[f"label_{h}d"] = (future_close / out["close"] - 1 >= target_return).astype("Int8")
    return out
