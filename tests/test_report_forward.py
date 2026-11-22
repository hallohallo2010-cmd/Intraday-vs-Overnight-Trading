"""The live paper-test box: correct counter, no verdict before the pre-registered threshold."""
import dataclasses

import pandas as pd
import pytest

from oviv.analysis import analyse
from oviv.config import load_config
from oviv.data import DataIssues, build_panel
from oviv.report import build, forward_status
from oviv.strategies import STRATEGIES
from tests.helpers import random_bars


@pytest.fixture(scope="module")
def results():
    cfg = dataclasses.replace(load_config(), basket=["T0", "T1", "T2"], benchmarks=[])
    raw = {t: random_bars(n=120, seed=i) for i, t in enumerate(cfg.basket)}
    issues = DataIssues()
    on, intra = build_panel(raw, issues)
    return analyse(on, intra, cfg, issues)


def _fwd(n):
    idx = pd.bdate_range("2026-11-23", periods=n, name="Date")
    df = pd.DataFrame({s: 0.001 for s in STRATEGIES}, index=idx)
    df["n_names"] = 50
    return df


def test_empty_log_shows_zero_and_no_verdict(results):
    html = forward_status(_fwd(0), results)
    assert "0 / 120" in html
    assert "no verdict yet" in html
    assert "aria-valuenow='0'" in html


def test_partial_log_shows_progress_and_cumulative_returns(results):
    html = forward_status(_fwd(23), results)
    assert "23 / 120" in html
    assert "no verdict yet" in html and "not used for any conclusion" in html
    assert f"{(1.001 ** 23 - 1) * 100:+.2f}%" in html
    assert "2026-11-23" in html


def test_verdict_only_allowed_after_threshold(results):
    assert "Verdict allowed" not in forward_status(_fwd(119), results)
    assert "Verdict allowed" in forward_status(_fwd(120), results)


def test_box_is_at_the_top_of_the_report(results, tmp_path):
    page = build(results, _fwd(5), tmp_path / "index.html").read_text()
    assert page.index("Live paper test") < page.index("Headline results")
    assert page.index("Verdict") < page.index("Live paper test")
