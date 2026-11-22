"""Equal-weight, daily-rebalanced basket strategies.

Timing (per name, per day t):
  * Buy & hold      : hold Close_{t-1} -> Close_t (overnight leg x intraday leg).
  * Overnight only  : buy at Close_{t-1}, sell at Open_t.   One round trip / day.
  * Intraday only   : buy at Open_t, sell at Close_t.       One round trip / day.

Every return for day t uses only prices printed on t-1 and t, so nothing
observed after the exit is used. The basket is the equal-weight mean across
names that have both legs on day t (weights are 1/N for that day).
"""
from __future__ import annotations

import pandas as pd

STRATEGIES = ["buy_hold", "overnight_gross", "overnight_net", "intraday_gross", "intraday_net"]
LABELS = {
    "buy_hold": "Buy & hold",
    "overnight_gross": "Overnight (gross)",
    "overnight_net": "Overnight (net)",
    "intraday_gross": "Intraday (gross)",
    "intraday_net": "Intraday (net)",
}


def apply_friction(gross: pd.Series | pd.DataFrame, friction: float):
    """Charge one round trip per day: net = gross - friction.

    Each trading day of the overnight or intraday strategy is exactly one buy and
    one sell of every name, so the cost is subtracted exactly once per day.
    """
    return gross - friction


def ticker_returns(on: pd.DataFrame, intra: pd.DataFrame, friction: float) -> dict[str, pd.DataFrame]:
    """Daily returns per ticker for each strategy (wide frames, NaN = not held)."""
    return {
        "buy_hold": (1 + on) * (1 + intra) - 1,
        "overnight_gross": on,
        "overnight_net": apply_friction(on, friction),
        "intraday_gross": intra,
        "intraday_net": apply_friction(intra, friction),
    }


def basket_returns(on: pd.DataFrame, intra: pd.DataFrame, friction: float) -> pd.DataFrame:
    """Equal-weight basket daily returns for every strategy.

    Days on which no name is usable are dropped.
    """
    per = ticker_returns(on, intra, friction)
    out = pd.DataFrame({k: v.mean(axis=1, skipna=True) for k, v in per.items()})
    out["n_names"] = on.notna().sum(axis=1)
    return out.loc[out["n_names"] > 0, STRATEGIES + ["n_names"]]
