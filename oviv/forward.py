"""Forward (out-of-sample) tracking, kept strictly separate from the backtest.

Only dates after ``backtest_end`` are ever written here, and the log is
append-only: once a day is recorded it is never revised. Pre-registered rule:
no verdict is drawn from forward data before ``forward_min_days`` trading days.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .config import ROOT, Config
from .data import DataIssues, build_panel, fetch_raw
from .strategies import STRATEGIES, basket_returns

log = logging.getLogger("oviv.forward")

FORWARD_DIR = ROOT / "forward"
LOG_PATH = FORWARD_DIR / "forward_log.csv"
LEGS_PATH = FORWARD_DIR / "forward_legs.csv"
NY = ZoneInfo("America/New_York")


def read_log(path: Path = LOG_PATH) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=STRATEGIES + ["n_names"], index=pd.DatetimeIndex([], name="Date"))
    return pd.read_csv(path, index_col="Date", parse_dates=True)


def last_complete_session(now: datetime | None = None) -> pd.Timestamp:
    """Latest date whose daily bar is final (after 17:00 New York time)."""
    now = (now or datetime.now(tz=NY)).astimezone(NY)
    day = now.date() if now.hour >= 17 else now.date() - timedelta(days=1)
    return pd.Timestamp(day)


def new_rows(
    raw: dict[str, pd.DataFrame], cfg: Config, after: pd.Timestamp, until: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Basket and per-ticker returns for dates in (after, until]."""
    on, intra = build_panel(raw, DataIssues())
    cols = [t for t in cfg.basket if t in on.columns]
    b = basket_returns(on[cols], intra[cols], cfg.friction)
    keep = (b.index > after) & (b.index <= until)
    legs = (
        pd.concat({"overnight": on, "intraday": intra}, axis=1)
        .stack(level=1, future_stack=True)
        .rename_axis(["Date", "ticker"])
        .dropna(how="all")
    )
    dates = legs.index.get_level_values("Date")
    legs = legs[(dates > after) & (dates <= until)]
    return b.loc[keep], legs


def update(cfg: Config, now: datetime | None = None) -> int:
    """Fetch recent bars, append any new forward days. Returns rows appended."""
    FORWARD_DIR.mkdir(exist_ok=True)
    existing = read_log()
    floor = pd.Timestamp(cfg.backtest_end)
    after = max(floor, existing.index.max()) if len(existing) else floor
    until = last_complete_session(now)
    if until <= after:
        log.info("Forward log is up to date (last %s).", after.date())
        return 0

    # A short look-back supplies the previous close for the first new day.
    fetch_start = str((after - pd.Timedelta(days=10)).date())
    fetch_end = str((until + pd.Timedelta(days=1)).date())
    raw = {}
    for t in cfg.basket:
        try:
            raw[t] = fetch_raw(t, fetch_start, fetch_end)
        except Exception as exc:  # one bad ticker must not stop the log
            log.warning("forward fetch failed for %s: %s", t, exc)
    if not raw:
        raise RuntimeError("No forward data could be fetched.")

    rows, legs = new_rows(raw, cfg, after, until)
    if rows.empty:
        log.info("No new completed sessions since %s.", after.date())
        return 0
    rows.to_csv(LOG_PATH, mode="a", header=not LOG_PATH.exists(), float_format="%.8f",
                index_label="Date")
    legs.to_csv(LEGS_PATH, mode="a", header=not LEGS_PATH.exists(), float_format="%.8f")
    log.info("Appended %d forward day(s): %s", len(rows), ", ".join(str(d.date()) for d in rows.index))
    return len(rows)
