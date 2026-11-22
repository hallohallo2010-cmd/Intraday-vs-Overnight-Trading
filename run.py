"""Overnight vs Intraday backtest.

    python run.py              # backtest from cached data (downloads what is missing)
    python run.py --refresh    # re-download all backtest data
    python run.py forward      # append new forward days, then rebuild the report
"""
from __future__ import annotations

import argparse
import logging
import sys

from oviv import forward, report
from oviv.analysis import analyse
from oviv.config import load_config
from oviv.data import DataIssues, build_panel, load_raw

log = logging.getLogger("oviv")


def backtest(cfg, refresh: bool = False):
    raw = {}
    for t in cfg.all_tickers:
        raw[t] = load_raw(t, cfg.start, cfg.backtest_end, refresh=refresh)
        log.debug("%s: %d bars", t, len(raw[t]))
    issues = DataIssues()
    on, intra = build_panel(raw, issues)
    return analyse(on, intra, cfg, issues)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="backtest", choices=["backtest", "forward"])
    ap.add_argument("--refresh", action="store_true", help="re-download backtest data")
    ap.add_argument("--config", default=None, help="path to config.yaml")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("oviv.data").setLevel(logging.INFO if args.verbose else logging.ERROR)
    cfg = load_config(args.config) if args.config else load_config()

    if args.command == "forward":
        logging.getLogger("oviv.forward").setLevel(logging.INFO)
        forward.update(cfg)

    res = backtest(cfg, refresh=args.refresh)
    report.write_csvs(res)
    path = report.build(res, forward.read_log())

    print(f"Backtest {res.basket.index[0].date()} -> {res.basket.index[-1].date()}, "
          f"{len(res.basket):,} days. Data issues: {res.issues.summary()}")
    print(res.full.to_string(float_format=lambda v: f"{v:,.4f}"))
    print()
    for line in res.verdict:
        print("-", line)
    print(f"\nReport written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
