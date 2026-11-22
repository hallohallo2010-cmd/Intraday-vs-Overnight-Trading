"""Cost sensitivity table and break-even costs."""
import numpy as np
import pandas as pd
import pytest

from oviv.analysis import break_even_costs, cost_sensitivity
from oviv.metrics import stats


def _rets(n=1000, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    return pd.DataFrame({
        "overnight_gross": rng.normal(0.0004, 0.007, n),
        "intraday_gross": rng.normal(0.0002, 0.010, n),
    }, index=idx)


def test_break_even_is_where_net_mean_sharpe_and_t_are_zero():
    r = _rets()
    be = break_even_costs(r["overnight_gross"])
    assert be["mean_bps"] == pytest.approx(r["overnight_gross"].mean() * 1e4)
    net = stats(r["overnight_gross"] - be["mean_bps"] / 1e4)
    assert net["sharpe"] == pytest.approx(0, abs=1e-9)
    assert net["t_stat"] == pytest.approx(0, abs=1e-9)


def test_cagr_break_even_has_zero_growth_and_sits_below_mean_break_even():
    r = _rets()
    be = break_even_costs(r["intraday_gross"])
    net = r["intraday_gross"] - be["cagr_bps"] / 1e4
    assert np.log1p(net).sum() == pytest.approx(0, abs=1e-8)
    assert be["cagr_bps"] < be["mean_bps"]  # volatility drag


def test_table_has_grid_plus_break_even_rows_and_matches_direct_calculation():
    r = _rets()
    grid = [0, 2, 4, 6, 8, 11, 15]
    table, be = cost_sensitivity(r, grid)
    for c in grid:
        assert float(c) in table.index
    for leg in ("overnight", "intraday"):
        assert be[leg]["mean_bps"] in table.index
        assert table.at[be[leg]["mean_bps"], (leg, "t_stat")] == 0.0  # exactly, not -0.00
    assert len(table) == len(grid) + 2
    assert list(table.index) == sorted(table.index)
    direct = stats(r["intraday_gross"] - 0.0011)
    assert table.at[11.0, ("intraday", "cagr")] == pytest.approx(direct["cagr"])
    assert table.at[11.0, ("intraday", "t_stat")] == pytest.approx(direct["t_stat"])
    assert table.at[0.0, ("overnight", "sharpe")] == pytest.approx(stats(r["overnight_gross"])["sharpe"])


def test_net_results_fall_monotonically_with_cost():
    table, _ = cost_sensitivity(_rets(), [0, 2, 4, 6, 8, 11, 15])
    for leg in ("overnight", "intraday"):
        for m in ("cagr", "sharpe", "t_stat"):
            assert table[(leg, m)].is_monotonic_decreasing
