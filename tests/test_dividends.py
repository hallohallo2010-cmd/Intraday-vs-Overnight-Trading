"""Dividends are credited to the overnight leg on (and only on) their ex-dates."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from oviv.data import DataIssues, build_panel, clean_bars, compute_legs, read_cache, split_adjust
from oviv.strategies import basket_returns
from tests.helpers import make_bars

DATA = Path(__file__).resolve().parent.parent / "data"


def test_dividend_lands_on_ex_date_overnight_only():
    # $1.00 dividend goes ex on day 3: price opens $1 lower, holder receives $1.
    opens = [100.0, 100.0, 99.0, 99.5]
    closes = [100.0, 100.0, 99.5, 100.0]
    df = make_bars(opens, closes, dividends=[0, 0, 1.0, 0])
    legs = compute_legs(df, df.index, "T", DataIssues())
    assert legs["overnight"].iloc[2] == pytest.approx((99.0 + 1.0) / 100.0 - 1)  # = 0, not -1%
    assert legs["intraday"].iloc[2] == pytest.approx(99.5 / 99.0 - 1)  # no dividend intraday
    # Neighbouring days carry no dividend.
    assert legs["overnight"].iloc[1] == pytest.approx(0.0)
    assert legs["overnight"].iloc[3] == pytest.approx(99.5 / 99.5 - 1)


def test_without_the_dividend_the_overnight_leg_would_be_understated():
    df = make_bars([100.0, 99.0], [100.0, 99.5], dividends=[0, 1.0])
    no_div = df.assign(Dividends=0.0)
    with_div = compute_legs(df, df.index, "T", DataIssues())["overnight"].iloc[1]
    without = compute_legs(no_div, df.index, "T", DataIssues())["overnight"].iloc[1]
    assert with_div - without == pytest.approx(1.0 / 100.0)  # exactly D / Close_{t-1}


def test_dividend_flows_through_to_the_overnight_basket():
    a = make_bars([100.0, 99.0], [100.0, 99.0], dividends=[0, 1.0])  # ex-date: (99 + 1) / 100 - 1 = 0
    b = make_bars([50.0, 51.0], [50.0, 51.0])  # +2% overnight
    on, intra = build_panel({"A": a, "B": b}, DataIssues())
    basket = basket_returns(on, intra, 0.0)
    assert basket["overnight_gross"].iloc[-1] == pytest.approx((0.0 + 0.02) / 2)
    # Had the dividend been ignored, A would show -1% and the basket +0.5%.
    assert basket["overnight_gross"].iloc[-1] != pytest.approx((-0.01 + 0.02) / 2)
    assert basket["intraday_gross"].iloc[-1] == pytest.approx(0.0)
    # Buy & hold receives the dividend too (via its overnight leg).
    assert basket["buy_hold"].iloc[-1] == pytest.approx((0.0 + 0.02) / 2)


@pytest.mark.skipif(not (DATA / "AAPL.csv").exists(), reason="cached data not present")
def test_real_example_aapl_ex_date_2020_08_07():
    """AAPL went ex-dividend on 2020-08-07 ($0.82, i.e. $0.205 on today's split basis)."""
    issues = DataIssues()
    raw = read_cache("AAPL", DATA).loc["2020-07-01":"2020-09-30"]
    adj = split_adjust(clean_bars(raw, "AAPL", issues), "AAPL", issues)
    legs = compute_legs(adj, adj.index, "AAPL", issues)
    ex = pd.Timestamp("2020-08-07")
    prev = adj.index[adj.index.get_loc(ex) - 1]
    div = adj.at[ex, "Dividends"]
    assert div == pytest.approx(0.205)
    assert legs.at[ex, "overnight"] == pytest.approx((adj.at[ex, "Open"] + div) / adj.at[prev, "Close"] - 1)
    assert legs.at[ex, "intraday"] == pytest.approx(adj.at[ex, "Close"] / adj.at[ex, "Open"] - 1)


@pytest.mark.skipif(not (DATA / "KO.csv").exists(), reason="cached data not present")
def test_every_ex_date_in_real_data_is_credited_exactly_once():
    """Across KO's full history the extra overnight return equals sum(D_t / Close_{t-1})."""
    issues = DataIssues()
    raw = read_cache("KO", DATA)
    adj = split_adjust(clean_bars(raw, "KO", issues), "KO", issues)
    cal = adj.index
    with_div = compute_legs(adj, cal, "KO", DataIssues())["overnight"]
    no_div = compute_legs(adj.assign(Dividends=0.0), cal, "KO", DataIssues())["overnight"]
    credited = (with_div - no_div).fillna(0.0)
    expected = (adj["Dividends"] / adj["Close"].shift(1)).fillna(0.0)
    n_ex = int((adj["Dividends"] > 0).sum())
    assert n_ex > 60  # KO pays quarterly
    assert int((credited.abs() > 1e-12).sum()) == n_ex - int(adj["Dividends"].iloc[0] > 0)
    np.testing.assert_allclose(credited.to_numpy(), expected.to_numpy(), atol=1e-12)
