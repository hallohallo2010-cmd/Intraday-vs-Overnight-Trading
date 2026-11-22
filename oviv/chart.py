"""Equity-curve chart (log scale), gross vs net, in light and dark variants."""
from __future__ import annotations

import base64
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .metrics import equity  # noqa: E402
from .strategies import LABELS  # noqa: E402

# Validated categorical slots 1-3 (blue, orange, aqua) per mode; gross = solid,
# net = dashed so identity never relies on colour alone.
THEMES = {
    "light": {"surface": "#fcfcfb", "text": "#0b0b0b", "muted": "#52514e", "grid": "#e4e3df",
              "series": ["#2a78d6", "#eb6834", "#1baf7a"]},
    "dark": {"surface": "#1a1a19", "text": "#f0efec", "muted": "#c3c2b7", "grid": "#33332f",
             "series": ["#3987e5", "#d95926", "#199e70"]},
}
STYLE = {
    "buy_hold": (0, "-"),
    "overnight_gross": (1, "-"),
    "overnight_net": (1, (0, (4, 2))),
    "intraday_gross": (2, "-"),
    "intraday_net": (2, (0, (4, 2))),
}


def equity_png(returns: pd.DataFrame, theme: str = "light", title: str | None = None) -> str:
    """Return a base64 PNG of growth of $1 for each strategy column."""
    th = THEMES[theme]
    fig, ax = plt.subplots(figsize=(10, 5.4), dpi=144)
    fig.patch.set_facecolor(th["surface"])
    ax.set_facecolor(th["surface"])

    for col, (slot, ls) in STYLE.items():
        if col not in returns:
            continue
        eq = equity(returns[col])
        ax.plot(eq.index, eq.values, color=th["series"][slot], linestyle=ls, linewidth=2,
                label=LABELS[col])
        ax.annotate(f"{LABELS[col]}  ${eq.iloc[-1]:,.2f}" if eq.iloc[-1] < 10 else
                    f"{LABELS[col]}  ${eq.iloc[-1]:,.0f}",
                    xy=(eq.index[-1], eq.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=8, color=th["text"])

    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"${v:,.2f}" if v < 1 else f"${v:,.0f}"))
    ax.grid(True, which="major", color=th["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(th["grid"])
    ax.tick_params(colors=th["muted"], labelsize=9)
    ax.set_ylabel("Growth of $1 (log scale)", color=th["muted"], fontsize=9)
    if title:
        ax.set_title(title, color=th["text"], fontsize=11, loc="left")
    leg = ax.legend(loc="upper left", frameon=False, fontsize=9)
    for text in leg.get_texts():
        text.set_color(th["text"])
    ax.margins(x=0.01)
    fig.subplots_adjust(right=0.80, left=0.08, top=0.93, bottom=0.08)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=th["surface"])
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()
