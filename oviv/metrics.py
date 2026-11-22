"""Performance statistics on daily simple returns."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

METRIC_COLS = ["days", "cagr", "vol", "sharpe", "max_dd", "hit_rate", "mean_bps", "t_stat"]


def equity(r: pd.Series) -> pd.Series:
    return (1 + r.fillna(0)).cumprod()


def max_drawdown(r: pd.Series) -> float:
    eq = equity(r.dropna())
    if eq.empty:
        return float("nan")
    return float((eq / eq.cummax() - 1).min())


def t_stat(r: pd.Series) -> float:
    """t-statistic of the mean daily return (H0: mean = 0)."""
    r = r.dropna()
    n = len(r)
    if n < 2:
        return float("nan")
    sd = r.std(ddof=1)
    return float(r.mean() / (sd / math.sqrt(n))) if sd > 0 else float("nan")


def stats(r: pd.Series, periods: int = 252) -> dict[str, float]:
    """CAGR, annualised vol, Sharpe (rf = 0), max drawdown, hit rate, t-stat."""
    r = r.dropna()
    n = len(r)
    if n == 0:
        return {k: float("nan") for k in METRIC_COLS} | {"days": 0}
    growth = float(np.prod(1 + r.to_numpy()))
    sd = r.std(ddof=1) if n > 1 else float("nan")
    return {
        "days": n,
        "cagr": growth ** (periods / n) - 1 if growth > 0 else -1.0,
        "vol": sd * math.sqrt(periods),
        "sharpe": r.mean() / sd * math.sqrt(periods) if sd and sd > 0 else float("nan"),
        "max_dd": max_drawdown(r),
        "hit_rate": float((r > 0).mean()),
        "mean_bps": float(r.mean() * 1e4),
        "t_stat": t_stat(r),
    }


def stats_table(df: pd.DataFrame, periods: int = 252) -> pd.DataFrame:
    return pd.DataFrame({c: stats(df[c], periods) for c in df.columns}).T[METRIC_COLS]


def halves(index: pd.DatetimeIndex) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Split a date index into two halves with equal numbers of days."""
    mid = len(index) // 2
    return index[:mid], index[mid:]
