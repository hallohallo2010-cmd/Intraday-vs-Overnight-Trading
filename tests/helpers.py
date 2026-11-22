import numpy as np
import pandas as pd


def make_bars(opens, closes, start="2024-01-02", dividends=None, splits=None):
    """Build a bar frame with High/Low bracketing Open/Close."""
    idx = pd.bdate_range(start, periods=len(opens))
    o = np.asarray(opens, float)
    c = np.asarray(closes, float)
    df = pd.DataFrame(
        {
            "Open": o,
            "High": np.maximum(o, c) * 1.01,
            "Low": np.minimum(o, c) * 0.99,
            "Close": c,
            "Volume": 1_000_000.0,
            "Dividends": 0.0 if dividends is None else np.asarray(dividends, float),
            "Stock Splits": 0.0 if splits is None else np.asarray(splits, float),
        },
        index=idx,
    )
    df.index.name = "Date"
    return df


def random_bars(n=300, seed=0, start="2020-01-01"):
    rng = np.random.default_rng(seed)
    on = rng.normal(0.0003, 0.008, n)
    intra = rng.normal(0.0001, 0.012, n)
    closes, opens = [], []
    prev = 100.0
    for a, b in zip(on, intra):
        o = prev * (1 + a)
        c = o * (1 + b)
        opens.append(o)
        closes.append(c)
        prev = c
    return make_bars(opens, closes, start=start)
