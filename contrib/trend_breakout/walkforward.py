"""
Rolling walk-forward test for TrendBreakoutStrategy: 12 months train, 6 months test, 6 month step.

For each window, a parameter grid is backtested on the train period. The cell with the best
neighbour-smoothed profit (more robust than the single best cell) is then backtested on the
following test period. The naive best cell and the strategy defaults are reported as well.

Usage (from the repo root, with 4h and 1d data downloaded for the config's pairs and BTC):
    python contrib/trend_breakout/walkforward.py <config.json> <results.json>

Each backtest runs in its own temporary strategy dir (strategy copy + params json),
so backtests can run in parallel.
"""

import itertools
import json
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


STRATEGY_FILE = Path(__file__).with_name("trend_breakout_strategy.py")
WINDOWS = [  # (train start, train end == test start, test end)
    ("20230901", "20240901", "20250301"),
    ("20240301", "20250301", "20250901"),
    ("20240901", "20250901", "20260301"),
    ("20250301", "20260301", "20261027"),
]
GRID = {"breakout_len": [20, 40, 60, 90, 120], "exit_len": [6, 12, 18, 24, 36]}
DEFAULT = (60, 18)
KEYS = list(GRID)
COMBOS = list(itertools.product(*GRID.values()))


def _metric(output: str, label: str) -> str | None:
    match = re.search(re.escape(label) + r"\s*│\s*([^│]+?)\s*│", output)
    return match.group(1).split()[0] if match else None


def _number(value: str | None) -> float:
    return float(value.rstrip("%")) if value else float("nan")


def backtest(config: str, combo: tuple, timerange: str) -> dict:
    params = dict(zip(KEYS, combo, strict=True))
    with tempfile.TemporaryDirectory() as strategy_dir:
        shutil.copy(STRATEGY_FILE, strategy_dir)
        Path(strategy_dir, "trend_breakout_strategy.json").write_text(
            json.dumps(
                {
                    "strategy_name": "TrendBreakoutStrategy",
                    "ft_stratparam_v": 1,
                    "params": {
                        "buy": {"breakout_len": params["breakout_len"]},
                        "sell": {"exit_len": params["exit_len"]},
                    },
                }
            )
        )
        output = subprocess.run(
            [
                "freqtrade", "backtesting", "-c", config, "-s", "TrendBreakoutStrategy",
                "--strategy-path", strategy_dir, "--timerange", timerange,
                "--no-color", "--export", "none",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout  # fmt: skip
    if _metric(output, "Total profit %") is None:
        raise RuntimeError(f"Backtest {combo} {timerange} produced no results:\n{output[-2000:]}")
    return {
        "trades": int(_metric(output, "Total/Daily Avg Trades") or 0),
        "profit_pct": _number(_metric(output, "Total profit %")),
        "abs_profit": _number(_metric(output, "Absolute profit")),
        "pf": _number(_metric(output, "Profit factor")),
        "dd_pct": _number(_metric(output, "Max % of account underwater")),
        "market_pct": _number(_metric(output, "Market change")),
    }


def neighbours(combo: tuple):
    idx = [GRID[k].index(v) for k, v in zip(KEYS, combo, strict=True)]
    for delta in itertools.product((-1, 0, 1), repeat=len(KEYS)):
        moved = [i + d for i, d in zip(idx, delta, strict=True)]
        if all(0 <= m < len(GRID[k]) for m, k in zip(moved, KEYS, strict=True)):
            yield tuple(GRID[k][m] for m, k in zip(moved, KEYS, strict=True))


def run_window(pool, config: str, n: int, train_start: str, test_start: str, test_end: str):
    train_range, test_range = f"{train_start}-{test_start}", f"{test_start}-{test_end}"
    train_results = pool.map(lambda c: backtest(config, c, train_range), COMBOS)
    train = dict(zip(COMBOS, train_results, strict=True))
    smooth = {}
    for combo in COMBOS:
        nbs = list(neighbours(combo))
        smooth[combo] = sum(train[nb]["profit_pct"] for nb in nbs) / len(nbs)
    robust = max(smooth, key=smooth.get)
    naive = max(COMBOS, key=lambda c: train[c]["profit_pct"])
    robust_t, naive_t, default_t = pool.map(
        lambda c: backtest(config, c, test_range), [robust, naive, DEFAULT]
    )
    return {
        "window": n,
        "train": train_range,
        "test": test_range,
        "robust_params": dict(zip(KEYS, robust, strict=True)),
        "robust_train": train[robust],
        "robust_smooth": smooth[robust],
        "naive_params": dict(zip(KEYS, naive, strict=True)),
        "naive_train": train[naive],
        "train_profitable_cells": sum(r["profit_pct"] > 0 for r in train.values()),
        "train_cells": len(train),
        "robust_test": robust_t,
        "naive_test": naive_t,
        "default_test": default_t,
        "train_grid": {"|".join(map(str, c)): r for c, r in train.items()},
    }


def main(config: str, out: Path) -> None:
    results = []
    with ThreadPoolExecutor(4) as pool:
        for n, (train_start, test_start, test_end) in enumerate(WINDOWS, 1):
            w = run_window(pool, config, n, train_start, test_start, test_end)
            results.append(w)
            out.write_text(json.dumps(results, indent=1))
            print(
                f"window {n} test {w['test']}: "
                f"robust {w['robust_params']} -> {w['robust_test']['profit_pct']}% | "
                f"naive {w['naive_params']} -> {w['naive_test']['profit_pct']}% | "
                f"default -> {w['default_test']['profit_pct']}% | "
                f"market {w['robust_test']['market_pct']}% | "
                f"train profitable {w['train_profitable_cells']}/{w['train_cells']}",
                flush=True,
            )
    for key in ("robust_test", "naive_test", "default_test"):
        total = sum(w[key]["abs_profit"] for w in results)
        print(f"{key}: stitched absolute profit {total:.1f}")


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
