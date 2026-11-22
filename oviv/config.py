from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    basket: list[str]
    benchmarks: list[str]
    start: str
    backtest_end: str
    friction_bps_round_trip: float
    edge_t_threshold: float
    forward_min_days: int
    trading_days_per_year: int
    cost_sensitivity_bps: tuple[float, ...] = (0, 2, 4, 6, 8, 11, 15)

    @property
    def friction(self) -> float:
        """Round-trip friction as a decimal return (11 bps -> 0.0011)."""
        return self.friction_bps_round_trip / 10_000

    @property
    def all_tickers(self) -> list[str]:
        return list(dict.fromkeys(self.basket + self.benchmarks))


def load_config(path: str | Path = ROOT / "config.yaml") -> Config:
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    return Config(
        basket=[str(t) for t in raw["basket"]],
        benchmarks=[str(t) for t in raw.get("benchmarks", [])],
        start=str(raw["start"]),
        backtest_end=str(raw["backtest_end"]),
        friction_bps_round_trip=float(raw.get("friction_bps_round_trip", 11)),
        edge_t_threshold=float(raw.get("edge_t_threshold", 2.0)),
        forward_min_days=int(raw.get("forward_min_days", 120)),
        trading_days_per_year=int(raw.get("trading_days_per_year", 252)),
        cost_sensitivity_bps=tuple(float(c) for c in raw.get("cost_sensitivity_bps", [0, 2, 4, 6, 8, 11, 15])),
    )
