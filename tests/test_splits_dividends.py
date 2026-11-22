"""Split and dividend handling on a known example."""
import math

import numpy as np
import pandas as pd
import pytest

from oviv.data import DataIssues, build_panel, compute_legs, split_adjust
from tests.helpers import make_bars

# Known example: a 4-for-1 split on day 3 and a $0.50 dividend (post-split basis)
# going ex on day 5. True economics:
#   day 3 overnight: pre-split close 400 -> open 101 post-split = 404 pre-split -> +1%
#   day 5 overnight: close 102, opens 101.5 ex-dividend, holder also gets 0.50
#                    -> (101.5 + 0.5) / 102 - 1 = 0
RAW_OPENS = [398.0, 399.0, 101.0, 101.0, 101.5]
RAW_CLOSES = [399.0, 400.0, 100.0, 102.0, 103.0]
SPLITS = [0, 0, 4.0, 0, 0]
DIVS = [0, 0, 0, 0, 0.5]


def _legs(df):
    issues = DataIssues()
    adj = split_adjust(df, "TEST", issues)
    return compute_legs(adj, df.index, "TEST", issues), issues


def test_raw_split_is_back_adjusted():
    df = make_bars(RAW_OPENS, RAW_CLOSES, dividends=DIVS, splits=SPLITS)
    legs, issues = _legs(df)
    assert legs["overnight"].iloc[2] == pytest.approx(101 * 4 / 400 - 1)  # +1%, not -75%
    assert legs["overnight"].iloc[1] == pytest.approx(399 / 399 - 1)
    assert "back-adjusted" in issues.split_decisions[0]["decision"]


def test_dividend_added_to_overnight_on_ex_date():
    df = make_bars(RAW_OPENS, RAW_CLOSES, dividends=DIVS, splits=SPLITS)
    legs, _ = _legs(df)
    assert legs["overnight"].iloc[4] == pytest.approx((101.5 + 0.5) / 102 - 1)
    # Dividend never leaks into the intraday leg.
    assert legs["intraday"].iloc[4] == pytest.approx(103 / 101.5 - 1)


def test_already_adjusted_vendor_data_is_not_double_adjusted():
    """Yahoo-style: prices before the split are already divided by 4."""
    pre = np.array([1, 1, 0, 0, 0], bool)
    opens = np.where(pre, np.array(RAW_OPENS) / 4, RAW_OPENS)
    closes = np.where(pre, np.array(RAW_CLOSES) / 4, RAW_CLOSES)
    adj_df = make_bars(opens, closes, dividends=DIVS, splits=SPLITS)
    raw_df = make_bars(RAW_OPENS, RAW_CLOSES, dividends=DIVS, splits=SPLITS)
    legs_adj, issues = _legs(adj_df)
    legs_raw, _ = _legs(raw_df)
    pd.testing.assert_frame_equal(legs_adj, legs_raw)
    assert "already split-adjusted" in issues.split_decisions[0]["decision"]


def test_pre_split_dividend_is_adjusted_with_prices():
    # Raw data with a $2.00 dividend (pre-split basis) on day 2, then 4:1 split.
    opens = [398.0, 397.0, 101.0]
    closes = [399.0, 400.0, 100.0]
    df = make_bars(opens, closes, dividends=[0, 2.0, 0], splits=[0, 0, 4.0])
    issues = DataIssues()
    adj = split_adjust(df, "T", issues)
    assert adj["Dividends"].iloc[1] == pytest.approx(0.5)
    assert adj["Close"].iloc[1] == pytest.approx(100.0)
    legs = compute_legs(adj, df.index, "T", issues)
    assert legs["overnight"].iloc[1] == pytest.approx((397 + 2) / 399 - 1)


def test_total_return_matches_dividend_reinvested_close_to_close():
    df = make_bars(RAW_OPENS, RAW_CLOSES, dividends=DIVS, splits=SPLITS)
    legs, _ = _legs(df)
    total = (1 + legs["overnight"]) * (1 + legs["intraday"]) - 1
    # Day 5: close-to-close with dividend reinvested at the open.
    expected = (103 + 0.5 * 103 / 101.5) / 102 - 1
    assert total.iloc[4] == pytest.approx(expected)


def test_missing_previous_bar_gives_no_overnight_return():
    df = make_bars([10, 11, 12, 13], [10.5, 11.5, 12.5, 13.5])
    calendar = df.index
    gapped = df.drop(df.index[1])
    issues = DataIssues()
    legs = compute_legs(gapped, calendar, "T", issues)
    assert math.isnan(legs["overnight"].iloc[2])  # would otherwise span 2 days
    assert legs["intraday"].isna().iloc[1]


def test_bad_bars_are_dropped_and_logged_not_filled():
    good = make_bars([10, 11, 12, 13], [10.5, 11.5, 12.5, 13.5])
    bad = good.copy()
    bad.iloc[2, bad.columns.get_loc("Close")] = -1.0
    other = make_bars([10, 11, 12, 13], [10.5, 11.5, 12.5, 13.5])
    issues = DataIssues()
    on, intra = build_panel({"BAD": bad, "OK": other}, issues)
    assert issues.bad_bars == [{"ticker": "BAD", "date": str(good.index[2].date()),
                                "reason": "non-positive price"}]
    assert on["BAD"].isna().iloc[2] and on["BAD"].isna().iloc[3]
    assert intra["BAD"].isna().iloc[2]
    assert on["OK"].notna().iloc[1:].all()


def test_missing_vendor_day_is_logged():
    a = make_bars([10, 11, 12, 13], [10.5, 11.5, 12.5, 13.5])
    b = a.drop(a.index[1])
    issues = DataIssues()
    build_panel({"A": a, "B": b}, issues)
    assert issues.missing_days == [{"ticker": "B", "date": str(a.index[1].date())}]
