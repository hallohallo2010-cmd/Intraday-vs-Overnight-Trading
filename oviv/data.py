"""Data loading, caching, cleaning, and split/dividend handling.

Price conventions
-----------------
We download with ``auto_adjust=False`` and use the raw ``Open``/``Close`` plus the
``Dividends`` and ``Stock Splits`` action columns. We never use ``Adj Close``.

Yahoo's "raw" Open/Close are in practice already *split*-adjusted (but not
dividend-adjusted), while other vendors deliver truly unadjusted prices. To be
correct for both, :func:`split_adjust` checks each split event against the
observed price gap and only back-adjusts when the series is still on the
pre-split basis. This prevents double adjustment.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT

log = logging.getLogger("oviv.data")

DATA_DIR = ROOT / "data"
PRICE_COLS = ["Open", "High", "Low", "Close"]
CACHE_COLS = ["Open", "High", "Low", "Close", "Volume", "Dividends", "Stock Splits"]

# A bar's Open/Close may sit marginally outside [Low, High] through rounding.
RANGE_TOL = 0.005
# An overnight or intraday move beyond this (in log terms) is treated as a bad
# print / missed corporate action and dropped: ln(2.5) ~ +150% / -60%.
# Real large-cap gaps (e.g. NFLX -37% in Oct 2011, MS +59% in Oct 2008) stay in.
MAX_ABS_LOG_MOVE = math.log(2.5)
# Moves beyond this are kept but logged for review: ln(1.3) ~ +30% / -23%.
REVIEW_ABS_LOG_MOVE = math.log(1.3)


@dataclass
class DataIssues:
    """Collects everything we dropped or decided, for the report."""

    bad_bars: list[dict] = field(default_factory=list)
    missing_days: list[dict] = field(default_factory=list)
    split_decisions: list[dict] = field(default_factory=list)
    outliers: list[dict] = field(default_factory=list)
    large_moves: list[dict] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {
            "bad_bars": len(self.bad_bars),
            "missing_days": len(self.missing_days),
            "splits": len(self.split_decisions),
            "outliers_dropped": len(self.outliers),
            "large_moves_kept": len(self.large_moves),
        }


# --------------------------------------------------------------------------- I/O
def cache_path(ticker: str, data_dir: Path = DATA_DIR) -> Path:
    return Path(data_dir) / f"{ticker}.csv"


def fetch_raw(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    """Download daily bars from yfinance with auto_adjust=False (raw prices)."""
    import yfinance as yf  # imported lazily so tests never need the network

    df = yf.Ticker(ticker).history(
        start=start, end=end, interval="1d", auto_adjust=False, actions=True
    )
    if df.empty:
        raise RuntimeError(f"No data returned for {ticker}")
    df.index = pd.DatetimeIndex(df.index.date, name="Date")
    for col in CACHE_COLS:
        if col not in df.columns:
            df[col] = 0.0
    return df[CACHE_COLS]


def save_cache(df: pd.DataFrame, ticker: str, data_dir: Path = DATA_DIR) -> None:
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path(ticker, data_dir), float_format="%.6f")


def read_cache(ticker: str, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    df = pd.read_csv(cache_path(ticker, data_dir), index_col="Date", parse_dates=True)
    return df[CACHE_COLS]


def load_raw(
    ticker: str,
    start: str,
    end: str | None,
    refresh: bool = False,
    data_dir: Path = DATA_DIR,
) -> pd.DataFrame:
    """Return raw bars for ``ticker`` from the CSV cache, downloading if needed.

    ``end`` is inclusive. The cache is only extended, never silently rewritten,
    unless ``refresh`` is set.
    """
    path = cache_path(ticker, data_dir)
    end_excl = None if end is None else str((pd.Timestamp(end) + pd.Timedelta(days=1)).date())
    if refresh or not path.exists():
        df = fetch_raw(ticker, start, end_excl)
        save_cache(df, ticker, data_dir)
    df = read_cache(ticker, data_dir)
    mask = df.index >= pd.Timestamp(start)
    if end is not None:
        mask &= df.index <= pd.Timestamp(end)
    return df.loc[mask].copy()


# ---------------------------------------------------------------------- cleaning
def clean_bars(df: pd.DataFrame, ticker: str, issues: DataIssues) -> pd.DataFrame:
    """Drop (never fill) bars that are unusable. Every drop is logged."""
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")].copy()
    df["Dividends"] = df["Dividends"].fillna(0.0)
    df["Stock Splits"] = df["Stock Splits"].fillna(0.0)

    o, h, l, c = (df[k] for k in PRICE_COLS)
    reasons = pd.Series("", index=df.index, dtype=object)

    def flag(mask: pd.Series, why: str) -> None:
        reasons[mask & (reasons == "")] = why

    flag(df[PRICE_COLS].isna().any(axis=1), "missing price")
    flag((df[PRICE_COLS] <= 0).any(axis=1), "non-positive price")
    flag(h < l, "high < low")
    flag((o > h * (1 + RANGE_TOL)) | (o < l * (1 - RANGE_TOL)), "open outside range")
    flag((c > h * (1 + RANGE_TOL)) | (c < l * (1 - RANGE_TOL)), "close outside range")
    flag(df["Dividends"] < 0, "negative dividend")

    bad = reasons != ""
    for dt, why in reasons[bad].items():
        issues.bad_bars.append({"ticker": ticker, "date": dt.date().isoformat(), "reason": why})
        log.warning("%s %s: dropped bad bar (%s)", ticker, dt.date(), why)
    return df.loc[~bad]


def find_missing_days(
    df: pd.DataFrame, calendar: pd.DatetimeIndex, ticker: str, issues: DataIssues
) -> list[pd.Timestamp]:
    """Log calendar days inside the ticker's own date range with no (clean) bar."""
    if df.empty:
        return []
    inside = calendar[(calendar >= df.index.min()) & (calendar <= df.index.max())]
    missing = inside.difference(df.index)
    for dt in missing:
        issues.missing_days.append({"ticker": ticker, "date": dt.date().isoformat()})
        log.warning("%s %s: missing day (not filled)", ticker, dt.date())
    return list(missing)


# ---------------------------------------------------------------------- splits
def split_adjust(df: pd.DataFrame, ticker: str, issues: DataIssues) -> pd.DataFrame:
    """Put all prices and dividends on one split basis (the latest one).

    ``Stock Splits`` holds the ratio on the ex-date (4.0 for a 4-for-1). If the
    observed overnight gap Open_t / Close_{t-1} looks like 1/ratio, the history is
    still on the pre-split basis and every earlier row is divided by the ratio.
    If the gap looks like a normal day, the vendor already adjusted it and we
    leave it alone. Prices and dividends are always adjusted together.
    """
    df = df.copy()
    events = df.index[(df["Stock Splits"] > 0) & (df["Stock Splits"] != 1.0)]
    for dt in events:
        ratio = float(df.at[dt, "Stock Splits"])
        pos = df.index.get_loc(dt)
        if pos == 0:
            decision = "no prior bar; assumed already adjusted"
        else:
            gap = df["Open"].iloc[pos] / df["Close"].iloc[pos - 1]
            raw_err = abs(math.log(gap * ratio))  # error if series is unadjusted
            adj_err = abs(math.log(gap))  # error if series is already adjusted
            if raw_err < adj_err:
                before = df.index < dt
                df.loc[before, PRICE_COLS] = df.loc[before, PRICE_COLS] / ratio
                df.loc[before, "Dividends"] = df.loc[before, "Dividends"] / ratio
                decision = "raw series: back-adjusted earlier prices and dividends"
            else:
                decision = "vendor already split-adjusted: no change"
        issues.split_decisions.append(
            {"ticker": ticker, "date": dt.date().isoformat(), "ratio": ratio, "decision": decision}
        )
        log.info("%s %s split %.4g: %s", ticker, dt.date(), ratio, decision)
    return df


# ---------------------------------------------------------------------- returns
def compute_legs(
    df: pd.DataFrame, calendar: pd.DatetimeIndex, ticker: str, issues: DataIssues
) -> pd.DataFrame:
    """Overnight and intraday returns on the master calendar.

    overnight_t = (Open_t + Div_t) / Close_{t-1} - 1   (dividend on its ex-date)
    intraday_t  = Close_t / Open_t - 1

    ``Close_{t-1}`` is the close of the previous *calendar* trading day. If that
    bar is missing or was dropped, the overnight return is undefined (NaN) rather
    than silently spanning several days. Nothing is forward-filled.
    """
    px = df.reindex(calendar)
    prev_close = px["Close"].shift(1)
    div = px["Dividends"].fillna(0.0)
    overnight = (px["Open"] + div) / prev_close - 1.0
    intraday = px["Close"] / px["Open"] - 1.0
    out = pd.DataFrame({"overnight": overnight, "intraday": intraday}, index=calendar)

    for leg in ("overnight", "intraday"):
        size = np.log1p(out[leg]).abs()
        review = (size > REVIEW_ABS_LOG_MOVE) & (size <= MAX_ABS_LOG_MOVE)
        for dt in out.index[review.fillna(False)]:
            issues.large_moves.append(
                {"ticker": ticker, "date": dt.date().isoformat(), "leg": leg,
                 "return": float(out.at[dt, leg])}
            )
        big = size > MAX_ABS_LOG_MOVE
        for dt in out.index[big.fillna(False)]:
            issues.outliers.append(
                {"ticker": ticker, "date": dt.date().isoformat(), "leg": leg,
                 "return": float(out.at[dt, leg])}
            )
            log.warning("%s %s: dropped implausible %s return %.1f%%",
                        ticker, dt.date(), leg, 100 * out.at[dt, leg])
        out.loc[big.fillna(False), leg] = np.nan

    # A ticker-day is usable only if both legs are known, so every strategy is
    # measured on exactly the same set of ticker-days.
    usable = out["overnight"].notna() & out["intraday"].notna()
    out.loc[~usable, :] = np.nan
    return out


def build_panel(
    raw: dict[str, pd.DataFrame], issues: DataIssues
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean every ticker and return (overnight, intraday) wide frames.

    The master calendar is the union of all dates any ticker traded on.
    """
    cleaned = {t: clean_bars(df, t, issues) for t, df in raw.items()}
    calendar = pd.DatetimeIndex(sorted(set().union(*[df.index for df in raw.values()])))
    on, intra = {}, {}
    for t, df in cleaned.items():
        # Missing = no bar at all from the vendor (dropped bad bars are logged separately).
        find_missing_days(raw[t], calendar, t, issues)
        adj = split_adjust(df, t, issues)
        legs = compute_legs(adj, calendar, t, issues)
        on[t], intra[t] = legs["overnight"], legs["intraday"]
    return pd.DataFrame(on, index=calendar), pd.DataFrame(intra, index=calendar)
