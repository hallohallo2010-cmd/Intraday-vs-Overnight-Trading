"""Static, self-contained HTML report for GitHub Pages (docs/index.html)."""
from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .analysis import Results
from .chart import equity_png
from .config import ROOT
from .metrics import stats_table
from .strategies import LABELS, STRATEGIES

DOCS = ROOT / "docs"

CSS = """
:root{--bg:#fcfcfb;--panel:#f4f3f0;--text:#0b0b0b;--text2:#52514e;--line:#e4e3df;
--good:#0a7d32;--bad:#b42318;--accent:#2a78d6;--warnbg:#fff6e0;--warnline:#eda100}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1a1a19;--panel:#232321;
--text:#f0efec;--text2:#c3c2b7;--line:#33332f;--good:#4cc27a;--bad:#f07a6e;--accent:#3987e5;
--warnbg:#2e2614;--warnline:#c98500}}
:root[data-theme="dark"]{--bg:#1a1a19;--panel:#232321;--text:#f0efec;--text2:#c3c2b7;--line:#33332f;
--good:#4cc27a;--bad:#f07a6e;--accent:#3987e5;--warnbg:#2e2614;--warnline:#c98500}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,-apple-system,"Segoe UI",
Roboto,sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 8px;padding-top:8px;
border-top:1px solid var(--line)}h3{font-size:15px;margin:18px 0 6px}
.sub{color:var(--text2);margin:0 0 20px}
.verdict{background:var(--panel);border-left:4px solid var(--accent);padding:14px 18px;border-radius:6px}
.verdict p{margin:6px 0}
.warn{background:var(--warnbg);border-left:4px solid var(--warnline);padding:10px 14px;border-radius:6px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:16px 0}
.tile{background:var(--panel);border-radius:6px;padding:10px 12px}
.tile .k{color:var(--text2);font-size:12px}.tile .v{font-size:22px;font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px;width:100%}
th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--text2);font-weight:600}
tr.be td{background:var(--warnbg);font-weight:600}tr.be td:first-child{border-left:3px solid var(--warnline)}
th.grp{text-align:center;border-bottom:1px solid var(--text2)}
td.pos,b.pos{color:var(--good)}td.neg,b.neg{color:var(--bad)}
.pass{color:var(--good);font-weight:600}.fail{color:var(--bad);font-weight:600}
img{max-width:100%;height:auto;display:block}
details{margin:8px 0}summary{cursor:pointer;color:var(--accent)}
small,.muted{color:var(--text2)}
a{color:var(--accent)}
.live{border:1px solid var(--line);border-radius:6px;padding:14px 18px;margin:16px 0;display:grid;gap:10px}
.live h3{margin:0;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.pill{font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--warnbg);
border:1px solid var(--warnline)}
.bar{height:8px;background:var(--panel);border-radius:4px;overflow:hidden}
.bar>span{display:block;height:100%;background:var(--accent)}
.live .row{display:flex;flex-wrap:wrap;gap:6px 18px;font-variant-numeric:tabular-nums}
.live p{margin:0}
"""

FMT = {
    "days": lambda v: f"{int(v):,}",
    "cagr": lambda v: f"{v * 100:+.2f}%",
    "vol": lambda v: f"{v * 100:.1f}%",
    "sharpe": lambda v: f"{v:+.2f}",
    "max_dd": lambda v: f"{v * 100:.1f}%",
    "hit_rate": lambda v: f"{v * 100:.1f}%",
    "mean_bps": lambda v: f"{v:+.2f}",
    "t_stat": lambda v: f"{v:+.2f}",
}
HEAD = {"days": "Days", "cagr": "CAGR", "vol": "Vol", "sharpe": "Sharpe", "max_dd": "Max DD",
        "hit_rate": "Hit rate", "mean_bps": "Mean (bps/day)", "t_stat": "t-stat"}
SIGNED = {"cagr", "sharpe", "mean_bps", "t_stat"}


def _cell(metric: str, v) -> str:
    if pd.isna(v):
        return "<td>–</td>"
    cls = ""
    if metric in SIGNED:
        cls = ' class="pos"' if v > 0 else ' class="neg"' if v < 0 else ""
    return f"<td{cls}>{FMT[metric](v)}</td>"


def metrics_table(df: pd.DataFrame, label_map: dict | None = None, first_col: str = "Strategy") -> str:
    cols = [c for c in FMT if c in df.columns]
    head = "".join(f"<th>{HEAD[c]}</th>" for c in cols)
    rows = []
    for idx, row in df.iterrows():
        name = (label_map or {}).get(idx, idx)
        rows.append(f"<tr><td>{html.escape(str(name))}</td>" + "".join(_cell(c, row[c]) for c in cols) + "</tr>")
    return (f'<div class="scroll"><table><thead><tr><th>{first_col}</th>{head}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>")


def year_table(ret: pd.DataFrame, tstat: pd.DataFrame) -> str:
    head = "".join(f"<th>{LABELS[s]}</th>" for s in STRATEGIES)
    rows = []
    for y in ret.index:
        cells = "".join(
            f'<td class="{"pos" if ret.at[y, s] > 0 else "neg"}">{ret.at[y, s] * 100:+.1f}%'
            f' <small>(t {tstat.at[y, s]:+.1f})</small></td>' for s in STRATEGIES)
        rows.append(f"<tr><td>{y}</td>{cells}</tr>")
    return (f'<div class="scroll"><table><thead><tr><th>Year</th>{head}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>")


def cost_table_html(r: Results) -> str:
    """Net CAGR / Sharpe / t-stat per leg across round-trip costs, break-evens marked."""
    t, be, base = r.cost_table, r.break_even, r.cfg.friction_bps_round_trip
    legs = [("overnight", "Overnight only"), ("intraday", "Intraday only")]
    marks = {v["mean_bps"]: leg for leg, v in be.items()}
    head1 = "<th></th>" + "".join(f'<th class="grp" colspan="3">{name} (net)</th>' for _, name in legs)
    head2 = "<th>Cost per round trip</th>" + "<th>CAGR</th><th>Sharpe</th><th>t-stat</th>" * 2
    rows = []
    for c in t.index:
        if c in marks:
            label, cls = f"{c:.2f} bps ← {marks[c]} break-even", ' class="be"'
        else:
            label, cls = f"{c:g} bps" + (" (base case)" if c == base else ""), ""
        cells = "".join(_cell(m, t.at[c, (leg, m)]) for leg, _ in legs for m in ("cagr", "sharpe", "t_stat"))
        rows.append(f"<tr{cls}><td>{label}</td>{cells}</tr>")
    note = (
        "<p class='muted'>Highlighted rows are the exact break-even costs: the net mean daily return, Sharpe "
        "and t-stat are zero there (cost = gross mean return per day). Net CAGR already turns negative a "
        f"little below that because of volatility drag: at {be['overnight']['cagr_bps']:.2f} bps overnight and "
        f"{be['intraday']['cagr_bps']:.2f} bps intraday. Every cost is charged once per trading day, "
        "since each leg is one round trip per day.</p>"
    )
    return (f'<div class="scroll"><table><thead><tr>{head1}</tr><tr>{head2}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>{note}")


def picture(returns: pd.DataFrame, alt: str) -> str:
    light, dark = equity_png(returns, "light"), equity_png(returns, "dark")
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="data:image/png;base64,{dark}">'
            f'<img alt="{html.escape(alt)}" src="data:image/png;base64,{light}"></picture>')


def forward_unblinded(n_days: int, need: int) -> bool:
    """Forward returns may be shown only once the pre-registered day count is reached."""
    return n_days >= need


def _progress(n: int, need: int) -> str:
    pct = min(100, round(100 * n / need))
    return (f"<div class='bar' role='progressbar' aria-valuemin='0' aria-valuemax='{need}' "
            f"aria-valuenow='{n}'><span style='width:{pct}%'></span></div>"
            f"<p><b>{n} / {need}</b> trading days recorded.</p>")


def forward_status(fwd: pd.DataFrame, r: Results) -> str:
    """Live paper-test box at the top of the page.

    Before the threshold it shows only the label, the progress bar and the day
    counter. No forward return, P&L or date-range detail is rendered, so nobody
    can peek at (or be swayed by) results before the pre-registered day count.
    """
    cfg = r.cfg
    n, need = len(fwd), cfg.forward_min_days
    if not forward_unblinded(n, need):
        return "\n".join([
            "<section class='live' aria-label='Live paper test'>",
            "<h3>Live paper test <span class='pill'>Collecting data, no verdict yet</span></h3>",
            _progress(n, need),
            "</section>",
        ])

    rets = fwd[STRATEGIES].astype(float)
    cum = (1 + rets).prod() - 1
    return "\n".join([
        "<section class='live' aria-label='Live paper test'>",
        "<h3>Live paper test <span class='pill'>Verdict allowed</span></h3>",
        "<p>Every weekday after the US close, the real open and close prices of that day are fetched and "
        "each strategy is scored on them. These are new prices the strategy never saw, not past data. "
        "No real orders are placed.</p>",
        _progress(n, need),
        f"<p>From {fwd.index[0].date()} to {fwd.index[-1].date()} (last update). Cumulative paper return:</p>",
        "<div class='row'>" + "".join(
            f"<span>{LABELS[s]}: <b class='{'pos' if cum[s] > 0 else 'neg' if cum[s] < 0 else ''}'>"
            f"{cum[s] * 100:+.2f}%</b></span>" for s in STRATEGIES) + "</div>",
        "<p class='muted'><a href='#forward'>Daily details and forward statistics</a></p>",
        "</section>",
    ])


def forward_section(fwd: pd.DataFrame, r: Results) -> str:
    cfg = r.cfg
    n, need = len(fwd), cfg.forward_min_days
    out = ["<h2 id='forward'>Forward tracking (out of sample)</h2>"]
    if not forward_unblinded(n, need):
        out += [
            "<p class='warn'><b>Pre-registered:</b> forward returns stay hidden on this page until "
            f"{need} trading days have been recorded. Then the full results appear here.</p>",
            _progress(n, need),
            f"<p class='muted'>Forward data starts after the backtest end ({cfg.backtest_end}). It is "
            "appended once per weekday by GitHub Actions, never revised, and never used in the backtest.</p>",
        ]
        return "\n".join(out)

    out += [
        f"<p class='warn'><b>Pre-registered threshold reached:</b> {n} / {need} trading days. "
        "The forward numbers may now be read as evidence.</p>",
        f"<p class='muted'>Forward data starts after the backtest end ({cfg.backtest_end}). It is "
        "appended once per weekday by GitHub Actions, never revised, and never used in the backtest.</p>",
    ]
    rets = fwd[STRATEGIES].astype(float)
    out.append(metrics_table(stats_table(rets, cfg.trading_days_per_year), LABELS))
    out.append(picture(rets, "Forward equity curves"))
    last = fwd.tail(10).iloc[::-1]
    head = "".join(f"<th>{LABELS[s]}</th>" for s in STRATEGIES)
    rows = "".join(
        f"<tr><td>{d.date()}</td>" + "".join(_cell("mean_bps", last.at[d, s] * 1e4) for s in STRATEGIES)
        + f"<td>{int(last.at[d, 'n_names'])}</td></tr>" for d in last.index)
    out.append(f"<h3>Latest days (bps)</h3><div class='scroll'><table><thead><tr><th>Date</th>{head}"
               f"<th>Names</th></tr></thead><tbody>{rows}</tbody></table></div>")
    return "\n".join(out)


def data_quality(r: Results) -> str:
    iss = r.issues
    s = iss.summary()
    parts = [
        "<h2>Data quality log</h2>",
        f"<p>{s['bad_bars']} bad bars dropped, {s['missing_days']} missing ticker-days, "
        f"{s['outliers_dropped']} implausible leg returns dropped (beyond +150% / −60%), "
        f"{s['large_moves_kept']} large but plausible moves kept (beyond +30% / −23%, listed for review), "
        f"{s['splits']} split events checked. Nothing was filled.</p>",
    ]

    def listing(title: str, rows: list[dict]) -> str:
        if not rows:
            return ""
        df = pd.DataFrame(rows)
        return (f"<details><summary>{title} ({len(rows)})</summary><div class='scroll'>"
                + df.to_html(index=False, border=0, float_format=lambda v: f"{v:.4f}") + "</div></details>")

    parts += [listing("Split decisions", iss.split_decisions), listing("Bad bars", iss.bad_bars),
              listing("Missing days", iss.missing_days), listing("Dropped outliers", iss.outliers),
              listing("Large moves kept (review)", iss.large_moves)]
    return "\n".join(parts)


def build(r: Results, fwd: pd.DataFrame, path: Path = DOCS / "index.html") -> Path:
    cfg = r.cfg
    b = r.basket
    start, end = b.index[0].date(), b.index[-1].date()
    (a1, b1), (a2, b2) = r.half_ranges
    f = r.full

    edge_rows = "".join(
        f"<tr><td>{LABELS[s]}</td><td>{e['h1_t']:+.2f}</td><td>{e['h2_t']:+.2f}</td>"
        f"<td class='{'pass' if e['edge'] else 'fail'}'>{'EDGE' if e['edge'] else 'NO EDGE'}</td></tr>"
        for s, e in r.edges.items())

    tiles = "".join(
        f"<div class='tile'><div class='k'>{LABELS[s]} CAGR</div><div class='v'>{f.at[s, 'cagr'] * 100:+.1f}%</div></div>"
        for s in STRATEGIES)

    per_ticker = []
    for s in STRATEGIES:
        df = r.per_ticker[s].copy()
        df.index = [f"{t} (benchmark)" if t in cfg.benchmarks else t for t in df.index]
        per_ticker.append(f"<details><summary>{LABELS[s]} — per ticker</summary>"
                          f"{metrics_table(df, first_col='Ticker')}</details>")

    body = f"""
<main>
<h1>Overnight vs Intraday</h1>
<p class="sub">Equal-weight basket of {len(cfg.basket)} large US stocks, rebalanced daily, {start} to {end}
({len(b):,} trading days). Friction {cfg.friction_bps_round_trip:g} bps per round trip.</p>

<section class="verdict"><h3 style="margin-top:0">Verdict</h3>
{''.join(f'<p>{html.escape(line)}</p>' for line in r.verdict)}
</section>

{forward_status(fwd, r)}

<div class="tiles">{tiles}</div>

<h2>Headline results (full sample)</h2>
{metrics_table(f, LABELS)}
<p class="muted">Sharpe uses a zero risk-free rate. t-stat tests whether the mean daily return differs from zero.
Buy &amp; hold is shown without trading costs (net = gross); it trades only to rebalance.</p>

<h2>Cost sensitivity</h2>
<p>How much can a round trip cost before trading a leg stops paying? Net results at each cost:</p>
{cost_table_html(r)}

<h2>Equity curves (log scale)</h2>
{picture(b[STRATEGIES], "Growth of $1 for each strategy, gross solid and net dashed, log scale")}
<p class="muted">Solid lines are gross, dashed lines are net of friction. Colour marks the strategy.</p>

<h2>Does it hold in both halves?</h2>
<p>An edge only counts if the <b>net</b> mean daily return is positive with t ≥ {cfg.edge_t_threshold:g}
in <b>both</b> halves of the sample.</p>
<div class="scroll"><table><thead><tr><th>Strategy</th><th>t, 1st half</th><th>t, 2nd half</th><th>Result</th></tr></thead>
<tbody>{edge_rows}</tbody></table></div>
<h3>First half: {a1} to {b1}</h3>
{metrics_table(r.first_half, LABELS)}
<h3>Second half: {a2} to {b2}</h3>
{metrics_table(r.second_half, LABELS)}

<h2>By year</h2>
<p class="muted">Calendar-year compounded return, with the t-stat of that year's mean daily return.</p>
{year_table(r.yearly_return, r.yearly_t)}

<h2>Per ticker</h2>
<p class="muted">Each ticker traded on its own over the days it has data. SPY and QQQ are benchmarks and are not in the basket.</p>
{''.join(per_ticker)}

{forward_section(fwd, r)}

<h2>Survivorship bias and other caveats</h2>
<ul>
<li><b>Survivorship bias.</b> The basket is today's list of large, successful companies. In {start.year} this
basket did not exist in this form: some names were small, some were not listed (they enter when their data starts),
and companies that shrank, were acquired or went bankrupt are absent. Absolute returns are therefore biased upward.
The <i>split</i> between overnight and intraday is less affected, but not immune.</li>
<li><b>Execution.</b> Fills at the official open and close are assumed. Real auction fills, slippage on
gaps and borrow/financing for an overnight position are folded into the single friction number.</li>
<li><b>Dividends</b> are credited to the overnight leg on the ex-date. Withholding taxes are ignored.</li>
<li><b>Splits.</b> Yahoo already split-adjusts its "raw" prices; each split is checked against the observed
gap so prices are adjusted exactly once (see the data quality log).</li>
<li><b>Risk-free rate</b> is taken as zero in the Sharpe ratio; the overnight strategy is in cash during the day
and vice versa, which would earn a little interest in practice.</li>
</ul>

{data_quality(r)}

<p class="muted" style="margin-top:32px">Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} by
<code>python run.py</code>. Full metric tables (including <code>cost_sensitivity.csv</code>) are in <code>docs/results/</code>.</p>
</main>"""

    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Overnight vs Intraday</title><style>{CSS}</style></head><body>{body}</body></html>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path


def write_csvs(r: Results, out: Path = DOCS / "results") -> None:
    out.mkdir(parents=True, exist_ok=True)
    fmt = "%.6f"  # rounded so library versions don't create diff noise
    r.full.to_csv(out / "strategy_full.csv", float_format=fmt)
    r.first_half.to_csv(out / "strategy_first_half.csv", float_format=fmt)
    r.second_half.to_csv(out / "strategy_second_half.csv", float_format=fmt)
    r.yearly_return.to_csv(out / "yearly_returns.csv", float_format=fmt)
    r.yearly_t.to_csv(out / "yearly_tstat.csv", float_format=fmt)
    pd.concat(r.per_ticker, names=["strategy", "ticker"]).to_csv(out / "per_ticker.csv", float_format=fmt)
    ct = r.cost_table.copy()
    ct.columns = [f"{leg}_net_{m}" for leg, m in ct.columns]
    ct.to_csv(out / "cost_sensitivity.csv", float_format=fmt)
    pd.DataFrame(r.break_even).T.rename_axis("leg").to_csv(out / "break_even_bps.csv", float_format=fmt)
    r.basket.to_csv(out / "basket_daily_returns.csv", float_format="%.8f")
