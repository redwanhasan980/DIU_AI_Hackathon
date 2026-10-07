"""Benchmark replicated synthetic feature rows, batched inference and DSO planning.

This measures computation on this machine, not ingestion, API concurrency or production SLA.
"""

from __future__ import annotations

import json
import platform
import time

import numpy as np
import pandas as pd

from floatwise.config import get_config
from floatwise.data.generate import load_dataset
from floatwise.engine.allocate import PLANNERS
from floatwise.engine.recommend import PolicyParams, recommend
from floatwise.features.build import build_panel, to_matrices
from floatwise.models.predict import QuantileModels


def main() -> None:
    cfg = get_config()
    data = load_dataset(cfg.data_dir)
    m = to_matrices(data["daily"])
    t = int(np.where(m.dates == pd.Timestamp(cfg.dates.demo_date))[0][0])
    start = time.perf_counter()
    panel = build_panel(cfg, m, data["calendar"], data["agents"], np.array([t]))
    feature_seconds = time.perf_counter() - start
    models = QuantileModels.load(cfg)
    h1 = panel[panel["h"] == 1]
    capacity = data["agents"].sort_values("agent_id")["float_capacity"].to_numpy()
    cash = (
        data["daily"]
        .loc[data["daily"]["date"] == m.dates[t]]
        .sort_values("agent_id")["close_cash"]
        .to_numpy()
    )
    rows = []
    for n in cfg.validation.benchmark_populations:
        runs = []
        for _ in range(cfg.validation.benchmark_repeats):
            started = time.perf_counter()
            # 7 horizons per agent, bounded batches; replication creates no independent agents.
            for offset in range(0, n * cfg.model.horizons, cfg.validation.benchmark_batch_size):
                idx = np.arange(
                    offset, min(offset + cfg.validation.benchmark_batch_size, n * cfg.model.horizons)
                ) % len(panel)
                batch = panel.iloc[idx]
                for target in cfg.model.targets:
                    models.predict_amount(batch, target)
            inference_seconds = time.perf_counter() - started
            preds = {target: models.predict_amount(h1, target) for target in cfg.model.targets}
            idx = np.arange(n) % len(capacity)
            started = time.perf_counter()
            rec = recommend(
                PolicyParams.from_config(cfg),
                cash[idx],
                capacity[idx] - cash[idx],
                capacity[idx],
                preds["cashout"][idx],
                preds["cashin"][idx],
            )
            recommendation_seconds = time.perf_counter() - started
            started = time.perf_counter()
            visits = 0
            for offset in range(0, n, cfg.network.agents_per_dso):
                sl = slice(offset, offset + cfg.network.agents_per_dso)
                plan = PLANNERS[cfg.policy.dso.allocator](
                    rec["action"][sl],
                    rec["cash_delta"][sl],
                    rec["expected_shortfall"][sl],
                    cfg.policy.dso.max_visits,
                    cfg.policy.dso.max_cash,
                )
                visits += len(plan.visits)
            runs.append(
                {
                    "inference_seconds": inference_seconds,
                    "recommendation_seconds": recommendation_seconds,
                    "planning_seconds": time.perf_counter() - started,
                    "visits": visits,
                }
            )
        rows.append(
            {
                "n_agents": n,
                "forecast_rows": n * cfg.model.horizons,
                "runs": runs,
                "median_seconds": {
                    k: round(float(np.median([r[k] for r in runs])), 4)
                    for k in ("inference_seconds", "recommendation_seconds", "planning_seconds")
                },
            }
        )
        print(f"benchmarked {n:,} replicated agents", flush=True)
    out = {
        "data_kind": "replicated_synthetic",
        "model_version": models.version,
        "machine": platform.platform(),
        "threads": cfg.model.inference_threads,
        "batch_size": cfg.validation.benchmark_batch_size,
        "repeats": cfg.validation.benchmark_repeats,
        "feature_build_500_agents_seconds": round(feature_seconds, 4),
        "limitations": "Feature construction timed only at original population. Larger runs replicate existing feature rows and balances; excludes streaming ingestion, database, HTTP, concurrency and retraining.",
        "populations": rows,
    }
    (cfg.artifacts_dir / "scale_benchmark.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
