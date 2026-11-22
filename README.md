# Overnight vs Intraday

Do US stock returns arrive **overnight** (previous close → open) or **intraday**
(open → close)? And can you trade either leg once costs are paid?

The answer, for an equal-weight basket of 50 large US stocks from 2005 to 2026,
is in [`docs/index.html`](docs/index.html) (published with GitHub Pages, see below).

## Quick start

```bash
python -m pip install -r requirements.txt   # Python 3.11+
python run.py                               # backtest + report
python -m pytest -q                         # tests
```

`python run.py` reads cached prices from `data/` (downloading any ticker that is
missing), runs the backtest, and writes:

* `docs/index.html`: the report, with a plain-language verdict at the top
* `docs/results/*.csv`: every metric table, plus the daily basket returns

Other commands:

| Command | What it does |
|---|---|
| `python run.py --refresh` | Re-download all backtest data from Yahoo Finance |
| `python run.py forward` | Append new forward days to `forward/`, then rebuild the report |
| `python run.py -v` | Log every split decision, dropped bar and missing day |

## Configuration

Edit [`config.yaml`](config.yaml):

* `basket`: the 50 stocks (equal weight, rebalanced daily)
* `benchmarks`: SPY and QQQ, reported per ticker but **not** in the basket
* `start`, `backtest_end`: the backtest window
* `friction_bps_round_trip`: cost per round trip (default 11 bps)
* `edge_t_threshold`: t-stat a net edge must reach in **both** halves (default 2)
* `forward_min_days`: forward days needed before any verdict (default 120)

After you add a ticker, run `python run.py` and it will be downloaded and cached.

## Method

**Data.** Daily bars from yfinance with `auto_adjust=False`. We use the raw
`Open`/`Close` with the `Dividends` and `Stock Splits` columns, and never
`Adj Close`. The raw download is cached per ticker in `data/<TICKER>.csv`.

**Returns** for each stock on day *t*:

* overnight = (Open<sub>t</sub> + Dividend<sub>t</sub>) / Close<sub>t−1</sub> − 1. The dividend counts on its ex-date, because that is the night the price drops by it.
* intraday = Close<sub>t</sub> / Open<sub>t</sub> − 1

**Splits.** All prices and dividends are put on one split basis. Yahoo's "raw"
prices are in fact already split-adjusted, while truly raw data is not. For each
split, the code compares the observed gap with the split ratio and back-adjusts
only if the series is still on the old basis. This way prices are never adjusted
twice. Every decision is listed in the report's data quality log.

**Bad data** is logged and dropped, never filled. That covers missing or
non-positive prices, high < low, and open or close outside the day's range. It
also covers impossible moves (beyond +150% or −60%), which usually mean a bad
print or a missed split. Large but real gaps, such as NFLX −37% in October 2011,
are kept and listed for review. If the previous day's bar is missing, there is no
overnight return for that day: it is not allowed to span two nights.

**Strategies** (equal weight across the names with data that day):

1. **Buy & hold**: close → close (both legs), no trading cost charged.
2. **Overnight only**: buy at the close, sell at the next open.
3. **Intraday only**: buy at the open, sell at the close.

Strategies 2 and 3 make one round trip per day, so net = gross − 11 bps every day.

**Statistics.** CAGR, annualised volatility, Sharpe (risk-free rate = 0), maximum
drawdown, hit rate, and the t-stat of the mean daily return. These are given for
the full sample, each half, each calendar year, and each ticker. An **edge only
counts if the net mean is positive with t ≥ 2 in both halves.**

**Survivorship bias.** The basket is today's list of large, successful companies.
Names that faded, were acquired or failed are absent. That inflates absolute
returns. The report says so prominently.

## Forward tracking (pre-registered)

`.github/workflows/forward.yml` runs every weekday at 22:15 UTC, after the US
close. It runs the tests, fetches the new bars, and appends the day to
`forward/forward_log.csv` (basket returns) and `forward/forward_legs.csv`
(per-ticker legs). Then it rebuilds the report and commits the changes.

Forward data is kept separate from the backtest. It covers only dates after
`backtest_end`, lives in `forward/` rather than `data/`, and is never fed into the
backtest. The log is append-only: a recorded day is never revised.

> **Pre-registration (written before any forward data existed):** no verdict
> will be drawn from forward data before **120 trading days** have been
> recorded. Until then, forward numbers are shown for transparency only. The
> rules for that verdict are fixed now and match the backtest. The strategies,
> the 11 bps friction and the edge test (positive net mean, t ≥ 2) stay as they
> are. `config.yaml` should not be changed during the forward period.

To run the workflow by hand: **Actions → Forward tracking → Run workflow**. It
needs write access, which `permissions: contents: write` grants. If your
organisation restricts it, enable **Settings → Actions → General → Workflow
permissions → Read and write**.

## Publishing the report with GitHub Pages

1. Merge this branch into your default branch (`main`).
2. Go to **Settings → Pages**.
3. Under **Build and deployment**, set **Source** to *Deploy from a branch*.
4. Pick branch `main` and folder **`/docs`**, then **Save**.
5. After a minute the report is live at `https://<user>.github.io/<repo>/`.

The forward workflow commits a fresh `docs/index.html` each weekday, and Pages
republishes it automatically.

## Tests

`python -m pytest -q` covers:

* **No look-ahead**: dropping or changing future prices leaves all earlier returns unchanged, and each day uses only Close<sub>t−1</sub> and day-*t* prices.
* **Splits and dividends** on a known example (a 4-for-1 split plus a dividend). Raw and vendor-adjusted inputs give identical returns, and the dividend lands on the overnight leg on its ex-date.
* **Friction** is charged exactly once per round trip: net = gross − cost every day, N days cost N round trips, and buy & hold pays none.
* **Data hygiene**: bad bars are dropped and not filled, missing days are logged, real gaps are kept, and impossible moves are dropped.
* **Forward**: only dates after the cutoff are written, and today's bar waits for the close.

## Layout

```
config.yaml          tickers and parameters
run.py               entry point
oviv/data.py         download, cache, cleaning, splits/dividends, leg returns
oviv/strategies.py   basket strategies and friction
oviv/metrics.py      CAGR, vol, Sharpe, drawdown, hit rate, t-stat
oviv/analysis.py     halves, years, per ticker, edge test, verdict
oviv/report.py       docs/index.html
oviv/chart.py        log-scale equity curves
oviv/forward.py      forward log (append-only)
data/                cached raw bars (backtest only)
forward/             forward log (never used by the backtest)
docs/                GitHub Pages site
tests/               pytest suite
```
