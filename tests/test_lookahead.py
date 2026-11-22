"""No look-ahead: day-t results depend only on data printed up to day t."""
import numpy as np
import pandas as pd

from oviv.data import DataIssues, build_panel
from oviv.strategies import basket_returns
from tests.helpers import random_bars

FRICTION = 0.0011


def _basket(raw):
    on, intra = build_panel(raw, DataIssues())
    return basket_returns(on, intra, FRICTION)


def _raw():
    return {f"T{i}": random_bars(n=250, seed=i) for i in range(5)}


def test_truncating_the_future_does_not_change_the_past():
    raw = _raw()
    full = _basket(raw)
    for cut in (50, 120, len(full) - 1):
        end = full.index[cut]
        part = _basket({t: df.loc[:end] for t, df in raw.items()})
        pd.testing.assert_frame_equal(part, full.loc[:end])


def test_perturbing_future_prices_does_not_change_the_past():
    raw = _raw()
    full = _basket(raw)
    cutoff = full.index[100]
    shocked = {}
    for t, df in raw.items():
        df = df.copy()
        df.loc[df.index > cutoff, ["Open", "High", "Low", "Close"]] *= 1.2  # change the future
        shocked[t] = df
    after = _basket(shocked)
    pd.testing.assert_frame_equal(after.loc[:cutoff], full.loc[:cutoff])
    nxt = full.index[101]
    assert after.at[nxt, "overnight_gross"] != full.at[nxt, "overnight_gross"]


def test_each_day_uses_only_previous_close_and_same_day_prices():
    raw = _raw()
    on, intra = build_panel(raw, DataIssues())
    df = raw["T0"]
    t = 10
    assert on["T0"].iloc[t] == (df["Open"].iloc[t] + df["Dividends"].iloc[t]) / df["Close"].iloc[t - 1] - 1
    assert intra["T0"].iloc[t] == df["Close"].iloc[t] / df["Open"].iloc[t] - 1
    # First day has no prior close: no overnight trade.
    assert np.isnan(on["T0"].iloc[0])
