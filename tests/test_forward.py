"""Forward tracking stays separate from the backtest and never uses partial bars."""
from datetime import datetime

import pandas as pd

from oviv.config import load_config
from oviv.forward import NY, last_complete_session, new_rows
from tests.helpers import random_bars


def test_only_dates_after_cutoff_are_emitted():
    cfg = load_config()
    raw = {t: random_bars(n=30, seed=i, start="2026-11-02") for i, t in enumerate(cfg.basket[:3])}
    idx = raw[cfg.basket[0]].index
    after, until = idx[20], idx[25]
    rows, legs = new_rows(raw, cfg, after, until)
    assert list(rows.index) == list(idx[21:26])
    dates = legs.index.get_level_values("Date")
    assert dates.min() > after and dates.max() <= until


def test_todays_bar_waits_for_the_close():
    during = datetime(2026, 11, 23, 15, 0, tzinfo=NY)  # Monday, market open
    after_close = datetime(2026, 11, 23, 18, 0, tzinfo=NY)
    assert last_complete_session(during) == pd.Timestamp("2026-11-22")
    assert last_complete_session(after_close) == pd.Timestamp("2026-11-23")
