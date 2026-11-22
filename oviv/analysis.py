"""Turns the return panel into the tables and verdict shown in the report."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import Config
from .data import DataIssues
from .metrics import halves, stats, stats_table
from .strategies import STRATEGIES, apply_friction, basket_returns, ticker_returns

TRADED = ["overnight_net", "intraday_net"]
LEGS = {"overnight": "overnight_gross", "intraday": "intraday_gross"}


@dataclass
class Results:
    cfg: Config
    basket: pd.DataFrame                      # daily basket returns per strategy
    full: pd.DataFrame                        # strategy x metric
    first_half: pd.DataFrame
    second_half: pd.DataFrame
    half_ranges: tuple[tuple[str, str], tuple[str, str]]
    yearly_return: pd.DataFrame               # year x strategy (compounded)
    yearly_t: pd.DataFrame                    # year x strategy (t-stat)
    per_ticker: dict[str, pd.DataFrame]       # strategy -> ticker x metric
    edges: dict[str, dict]                    # traded strategy -> edge test
    decomposition: dict[str, float]
    issues: DataIssues
    cost_table: pd.DataFrame = None           # rows: cost (bps); cols: (leg, metric)
    break_even: dict[str, dict] = None        # leg -> {"mean_bps", "cagr_bps"}
    verdict: list[str] = field(default_factory=list)


def _edge_test(first: pd.DataFrame, second: pd.DataFrame, strat: str, thr: float) -> dict:
    h1, h2 = first.loc[strat], second.loc[strat]
    ok1 = bool(h1["mean_bps"] > 0 and h1["t_stat"] >= thr)
    ok2 = bool(h2["mean_bps"] > 0 and h2["t_stat"] >= thr)
    return {"h1_t": float(h1["t_stat"]), "h2_t": float(h2["t_stat"]),
            "h1_ok": ok1, "h2_ok": ok2, "edge": ok1 and ok2}


def break_even_costs(gross: pd.Series) -> dict[str, float]:
    """Round-trip cost (bps) at which a daily-traded leg stops paying.

    ``mean_bps``: net = gross - c, so the net mean, Sharpe and t-stat are all
    exactly zero at c = mean(gross).
    ``cagr_bps``: the cost at which net CAGR is zero, i.e. sum(log(1 + g - c)) = 0.
    It is lower than ``mean_bps`` because of volatility drag (bisection).
    """
    g = gross.dropna().to_numpy()
    mean = float(g.mean())

    def growth(c: float) -> float:
        x = 1 + g - c
        return float(np.log(x).sum()) if (x > 0).all() else -np.inf

    lo, hi = min(0.0, mean) - 0.01, mean
    if growth(lo) <= 0:
        cagr_c = float("nan")
    else:
        for _ in range(200):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if growth(mid) > 0 else (lo, mid)
        cagr_c = (lo + hi) / 2
    return {"mean_bps": mean * 1e4, "cagr_bps": cagr_c * 1e4}


def cost_sensitivity(
    rets: pd.DataFrame, costs_bps: list[float], periods: int = 252
) -> tuple[pd.DataFrame, dict[str, dict]]:
    """Net CAGR, Sharpe and t-stat of each traded leg at each round-trip cost.

    The exact break-even cost of each leg (net mean = 0) is added as an extra
    row, so the table shows where the sign flips rather than only bracketing it.
    """
    be = {leg: break_even_costs(rets[col]) for leg, col in LEGS.items()}
    grid = sorted(set(float(c) for c in costs_bps) | {v["mean_bps"] for v in be.values()})
    rows = {}
    for c in grid:
        row = {}
        for leg, col in LEGS.items():
            st = stats(apply_friction(rets[col], c / 1e4), periods)
            row.update({(leg, "cagr"): st["cagr"], (leg, "sharpe"): st["sharpe"],
                        (leg, "t_stat"): st["t_stat"]})
        rows[c] = row
    table = pd.DataFrame(rows).T
    table.columns = pd.MultiIndex.from_tuples(table.columns)
    table.index.name = "cost_bps"
    table = table.mask(table.abs() < 1e-12, 0.0)  # print exact zeros, not -0.000
    return table, be


def _per_ticker(on: pd.DataFrame, intra: pd.DataFrame, cfg: Config) -> dict[str, pd.DataFrame]:
    per = ticker_returns(on, intra, cfg.friction)
    out = {}
    for strat, wide in per.items():
        rows = {t: stats(wide[t], cfg.trading_days_per_year) for t in wide.columns}
        out[strat] = pd.DataFrame(rows).T
    return out


def analyse(on: pd.DataFrame, intra: pd.DataFrame, cfg: Config, issues: DataIssues) -> Results:
    basket_cols = [t for t in cfg.basket if t in on.columns]
    b = basket_returns(on[basket_cols], intra[basket_cols], cfg.friction)
    rets = b[STRATEGIES]
    p = cfg.trading_days_per_year

    i1, i2 = halves(rets.index)
    first, second = stats_table(rets.loc[i1], p), stats_table(rets.loc[i2], p)

    year = rets.index.year
    yearly_return = rets.groupby(year).apply(lambda g: (1 + g).prod() - 1)
    yearly_t = rets.groupby(year).agg(lambda s: stats(s, p)["t_stat"])

    edges = {s: _edge_test(first, second, s, cfg.edge_t_threshold) for s in TRADED}

    log_on = float(np.log1p(rets["overnight_gross"]).sum())
    log_id = float(np.log1p(rets["intraday_gross"]).sum())
    decomposition = {
        "overnight_cum": float(np.expm1(log_on)),
        "intraday_cum": float(np.expm1(log_id)),
        "buy_hold_cum": float((1 + rets["buy_hold"]).prod() - 1),
        "overnight_log": log_on,
        "intraday_log": log_id,
    }

    cost_table, break_even = cost_sensitivity(rets, list(cfg.cost_sensitivity_bps), p)

    res = Results(
        cfg=cfg,
        basket=b,
        full=stats_table(rets, p),
        first_half=first,
        second_half=second,
        half_ranges=((str(i1[0].date()), str(i1[-1].date())), (str(i2[0].date()), str(i2[-1].date()))),
        yearly_return=yearly_return,
        yearly_t=yearly_t,
        per_ticker=_per_ticker(on, intra, cfg),
        edges=edges,
        decomposition=decomposition,
        issues=issues,
        cost_table=cost_table,
        break_even=break_even,
    )
    res.verdict = write_verdict(res)
    return res


def _pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:+.{digits}f}%"


def write_verdict(r: Results) -> list[str]:
    """Plain-language conclusions, derived only from the numbers."""
    f, d, cfg = r.full, r.decomposition, r.cfg
    start, end = r.basket.index[0].year, r.basket.index[-1].year
    total = d["overnight_log"] + d["intraday_log"]
    lines = []

    if d["overnight_log"] > d["intraday_log"]:
        where = "overnight (close to next open)"
    else:
        where = "intraday (open to close)"
    share = d["overnight_log"] / total if total > 0 else float("nan")
    lines.append(
        f"From {start} to {end}, the equal-weight basket's return came mostly {where}. "
        f"Overnight-only compounded at {_pct(f.at['overnight_gross', 'cagr'])} a year before costs, "
        f"intraday-only at {_pct(f.at['intraday_gross', 'cagr'])}, and buy & hold at "
        f"{_pct(f.at['buy_hold', 'cagr'])}"
        + (f" (the overnight leg accounts for {share * 100:.0f}% of the log return)." if total > 0 else ".")
    )

    lines.append(
        f"After {cfg.friction_bps_round_trip:g} bps per round trip (paid every trading day, about "
        f"{cfg.friction * cfg.trading_days_per_year * 100:.0f}% a year), overnight-only returns "
        f"{_pct(f.at['overnight_net', 'cagr'])} a year and intraday-only "
        f"{_pct(f.at['intraday_net', 'cagr'])}. Break-even is about "
        f"{r.break_even['overnight']['mean_bps']:.1f} bps per round trip overnight and "
        f"{r.break_even['intraday']['mean_bps']:.1f} bps intraday (where the net mean, Sharpe and t-stat "
        f"hit zero; net CAGR turns negative a little earlier, at "
        f"{r.break_even['overnight']['cagr_bps']:.1f} and {r.break_even['intraday']['cagr_bps']:.1f} bps)."
    )

    names = {"overnight_net": "Overnight", "intraday_net": "Intraday"}
    for s, e in r.edges.items():
        if e["edge"]:
            lines.append(
                f"{names[s]}-only net of costs passes the edge test: positive with t ≥ "
                f"{cfg.edge_t_threshold:g} in both halves (t = {e['h1_t']:.1f} and {e['h2_t']:.1f})."
            )
        else:
            lines.append(
                f"{names[s]}-only net of costs does not survive: it needs a positive mean with t ≥ "
                f"{cfg.edge_t_threshold:g} in both halves, and got t = {e['h1_t']:.1f} and {e['h2_t']:.1f}."
            )

    if not any(e["edge"] for e in r.edges.values()):
        lines.append(
            "Bottom line: the overnight effect is real as a description of where returns arrive, "
            "but neither leg is a tradable edge at this cost."
            + (" Simply holding through both legs did better than trading either one."
               if f.at["buy_hold", "cagr"] > max(f.at["overnight_net", "cagr"], f.at["intraday_net", "cagr"])
               else "")
        )
    lines.append(
        "Caveat: the basket is today's large caps, picked with hindsight (survivorship bias), "
        "so every absolute return here is flattered. The overnight vs intraday split is less exposed to that."
    )
    return lines
