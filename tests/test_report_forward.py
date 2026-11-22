"""Forward results stay blinded on the page until the pre-registered day count.

Before day 120 the page may show only the progress bar, the "X / 120" counter and
the "Collecting data, no verdict yet" label. No forward return or P&L may appear
anywhere in the rendered HTML. From day 120 the results are shown.
"""
import dataclasses
import re

import pandas as pd
import pytest

from oviv.analysis import analyse
from oviv.config import load_config
from oviv.data import DataIssues, build_panel
from oviv.report import build, forward_status
from oviv.strategies import STRATEGIES
from tests.helpers import random_bars

NEED = 120
UP, DOWN = 0.0123, -0.0456  # distinctive daily returns: +123 bps / -456 bps


@pytest.fixture(scope="module")
def results():
    cfg = dataclasses.replace(load_config(), basket=["T0", "T1", "T2"], benchmarks=[],
                              forward_min_days=NEED)
    raw = {t: random_bars(n=120, seed=i) for i, t in enumerate(cfg.basket)}
    issues = DataIssues()
    on, intra = build_panel(raw, issues)
    return analyse(on, intra, cfg, issues)


def _fwd(n, daily=UP):
    idx = pd.bdate_range("2026-11-23", periods=n, name="Date")
    df = pd.DataFrame({s: daily for s in STRATEGIES}, index=idx)
    df["n_names"] = 50
    return df


def _page(results, fwd, tmp_path, name):
    text = build(results, fwd, tmp_path / f"{name}.html").read_text()
    return re.sub(r"Generated \d{4}-\d\d-\d\d \d\d:\d\d UTC", "Generated <ts>", text)


def _return_strings(n, daily):
    cum = (1 + daily) ** n - 1
    return [f"{cum * 100:+.2f}%", f"{daily * 1e4:+.2f}", "Latest days", "Forward equity curves",
            "Cumulative paper return"]


@pytest.mark.parametrize("n", [0, 1, 23, NEED - 1])
def test_no_forward_returns_anywhere_before_day_120(results, tmp_path, n):
    up = _page(results, _fwd(n, UP), tmp_path, "up")
    down = _page(results, _fwd(n, DOWN), tmp_path, "down")
    # The strongest check: wildly different forward returns give the same page.
    assert up == down
    for s in _return_strings(n, UP) + _return_strings(n, DOWN):
        assert s not in up, f"forward result {s!r} leaked at day {n}"
    assert up.count("<picture") == 1  # only the backtest chart
    assert f"{n} / {NEED}" in up
    assert "Collecting data, no verdict yet" in up
    assert f"aria-valuenow='{n}'" in up


@pytest.mark.parametrize("n", [NEED, NEED + 15])
def test_forward_returns_appear_from_day_120(results, tmp_path, n):
    up = _page(results, _fwd(n, UP), tmp_path, "up")
    down = _page(results, _fwd(n, DOWN), tmp_path, "down")
    assert up != down
    for s in _return_strings(n, UP):
        assert s in up, f"forward result {s!r} missing at day {n}"
    assert up.count("<picture") == 2  # backtest chart + forward chart
    assert "Verdict allowed" in up
    assert "Collecting data, no verdict yet" not in up


def test_status_box_before_threshold_has_only_bar_counter_and_label(results):
    box = forward_status(_fwd(NEED - 1), results)
    text = re.sub(r"<[^>]+>", " ", box).split()
    assert " ".join(text) == f"Live paper test Collecting data, no verdict yet {NEED - 1} / {NEED} trading days recorded."
    assert "class='bar'" in box


def test_box_is_at_the_top_of_the_report(results, tmp_path):
    page = _page(results, _fwd(5), tmp_path, "top")
    assert page.index("Verdict") < page.index("Live paper test") < page.index("Headline results")
