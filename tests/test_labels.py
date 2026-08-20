import pandas as pd
from app.labels import add_forward_labels

def test_forward_label_uses_future_close():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=8, freq="D"),
        "close": [100, 100, 100, 100, 100, 103, 100, 100],
    })
    out = add_forward_labels(df, horizons=(5,), target_return=0.02)
    assert out.loc[0, "label_5d"] == 1
