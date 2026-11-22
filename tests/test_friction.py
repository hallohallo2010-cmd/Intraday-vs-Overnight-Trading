"""Friction is charged exactly once per round trip."""
import numpy as np
import pandas as pd
import pytest

from oviv.data import DataIssues, build_panel
from oviv.strategies import basket_returns, ticker_returns
from tests.helpers import make_bars, random_bars

FRICTION = 0.0011


def test_net_equals_gross_minus_one_round_trip_per_day():
    raw = {f"T{i}": random_bars(n=200, seed=i) for i in range(4)}
    on, intra = build_panel(raw, DataIssues())
    b = basket_returns(on, intra, FRICTION)
    np.testing.assert_allclose(b["overnight_gross"] - b["overnight_net"], FRICTION, atol=1e-15)
    np.testing.assert_allclose(b["intraday_gross"] - b["intraday_net"], FRICTION, atol=1e-15)


def test_total_cost_over_n_days_is_n_round_trips():
    # Flat prices: gross is exactly zero, so net compounds only the cost.
    n = 21
    df = make_bars([100.0] * n, [100.0] * n)
    on, intra = build_panel({"FLAT": df}, DataIssues())
    b = basket_returns(on, intra, FRICTION)
    assert len(b) == n - 1  # first day has no overnight leg
    assert b["overnight_gross"].abs().max() == 0
    assert (1 + b["overnight_net"]).prod() == pytest.approx((1 - FRICTION) ** (n - 1))
    assert b["intraday_net"].sum() == pytest.approx(-FRICTION * (n - 1))


def test_buy_and_hold_pays_no_round_trip_friction():
    raw = {"A": random_bars(n=50, seed=1)}
    on, intra = build_panel(raw, DataIssues())
    per = ticker_returns(on, intra, FRICTION)
    expected = (1 + on) * (1 + intra) - 1
    pd.testing.assert_frame_equal(per["buy_hold"], expected)


def test_friction_is_not_scaled_by_number_of_names():
    """Equal weights sum to 1, so the basket pays one round trip, not N."""
    raw = {f"T{i}": random_bars(n=30, seed=i) for i in range(10)}
    on, intra = build_panel(raw, DataIssues())
    b = basket_returns(on, intra, FRICTION)
    assert (b["intraday_gross"] - b["intraday_net"]).max() == pytest.approx(FRICTION)
