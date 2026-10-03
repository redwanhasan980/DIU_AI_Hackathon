"""Choose the FloatWise policy defaults on the VALIDATION period only (R-ML-1).

Grid over service level and risk threshold; rule: maximise stockout reduction vs status quo subject to
rebalancing trips <= +15 % and average cash held <= +5 %. Writes artifacts/policy_tuning.json.
Run after `make evaluate`: python scripts/tune_policy.py  (then copy the selection into config.yaml)
"""

from __future__ import annotations

import json

import pandas as pd

from floatwise.config import get_config
from floatwise.data.generate import load_dataset
from floatwise.engine.recommend import PolicyParams
from floatwise.simulation.backtest import load_inputs, policy_metrics, run_policy

GRID_S = [0.90, 0.95, 0.97, 0.98, 0.99]
GRID_THETA = [0.1, 0.2, 0.3]
MAX_EXTRA_TRIPS_PCT = 15.0
MAX_EXTRA_CASH_PCT = 5.0


def main() -> None:
    cfg = get_config()
    data = load_dataset(cfg.data_dir)
    forecasts = pd.read_parquet(cfg.artifacts_dir / "forecasts.parquet")
    inp = load_inputs(cfg, data, forecasts, cfg.dates.val_start, cfg.dates.val_end)
    sq = policy_metrics(cfg, inp, run_policy(cfg, inp, "status_quo"))
    rows = []
    for s in GRID_S:
        for th in GRID_THETA:
            p = PolicyParams.from_config(cfg, service_level=s, risk_threshold=th)
            m = policy_metrics(cfg, inp, run_policy(cfg, inp, "floatwise", p))
            rows.append({
                "service_level": s,
                "risk_threshold": th,
                "stockout_reduction_pct": round(100 * (1 - m["stockout_agent_days"] / sq["stockout_agent_days"]), 1),
                "extra_trips_pct": round(100 * (m["rebalancing_trips"] / sq["rebalancing_trips"] - 1), 1),
                "extra_cash_pct": round(100 * (m["avg_cash_held_bdt"] / sq["avg_cash_held_bdt"] - 1), 1),
            })  # fmt: skip
            print(rows[-1])
    ok = [
        r
        for r in rows
        if r["extra_trips_pct"] <= MAX_EXTRA_TRIPS_PCT and r["extra_cash_pct"] <= MAX_EXTRA_CASH_PCT
    ]
    best = max(ok, key=lambda r: r["stockout_reduction_pct"])
    out = {
        "period": f"{cfg.dates.val_start} → {cfg.dates.val_end} (validation)",
        "rule": f"max stockout reduction s.t. trips <= +{MAX_EXTRA_TRIPS_PCT}% and cash held <= +{MAX_EXTRA_CASH_PCT}%",
        "status_quo": sq,
        "grid": rows,
        "selected": best,
    }
    (cfg.artifacts_dir / "policy_tuning.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("selected:", best)


if __name__ == "__main__":
    main()
