"""FR-ALLOC-4: greedy vs exact (knapsack) DSO allocation in the backtest.

The default allocator is chosen on the VALIDATION period (R-ML-1); test results are reported for both.
Writes artifacts/allocator_comparison.json. Run after `make evaluate`: python scripts/compare_allocators.py
"""

from __future__ import annotations

import json
import time

import pandas as pd

from floatwise.config import get_config
from floatwise.data.generate import load_dataset
from floatwise.engine.recommend import PolicyParams
from floatwise.simulation.backtest import load_inputs, policy_metrics, run_policy

KEYS = (
    "stockout_agent_days",
    "failed_cashout_bdt",
    "failed_cashin_bdt",
    "avg_cash_held_bdt",
    "rebalancing_trips",
)


def main() -> None:
    cfg = get_config()
    data = load_dataset(cfg.data_dir)
    forecasts = pd.read_parquet(cfg.artifacts_dir / "forecasts.parquet")
    params = PolicyParams.from_config(cfg)
    out: dict = {}
    periods = {
        "validation": (cfg.dates.val_start, cfg.dates.val_end),
        "test": (cfg.dates.test_start, cfg.dates.test_end),
    }
    for name, (start, end) in periods.items():
        inp = load_inputs(cfg, data, forecasts, start, end)
        out[name] = {}
        for allocator in ("greedy", "optimal"):
            t0 = time.time()
            m = policy_metrics(cfg, inp, run_policy(cfg, inp, "floatwise", params, allocator=allocator))
            out[name][allocator] = {k: m[k] for k in KEYS} | {"seconds": round(time.time() - t0, 1)}
            print(name, allocator, out[name][allocator])
    v = out["validation"]
    better = v["optimal"]["stockout_agent_days"] < v["greedy"]["stockout_agent_days"]
    out["selected"] = "optimal" if better else "greedy"
    out["rule"] = "choose the allocator with fewer stockout agent-days on the validation period"
    (cfg.artifacts_dir / "allocator_comparison.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("selected:", out["selected"])


if __name__ == "__main__":
    main()
