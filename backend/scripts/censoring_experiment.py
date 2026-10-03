"""FR-FCST-6 experiment: how should training treat days censored by a stockout?

Observed volume on a stockout day understates true demand. We compare training choices on a
*held-out Eid* (Eid-ul-Fitr and Eid-ul-Adha 2025) with models trained only on data before 2025-03-01,
so the test period is never used for this decision (R-ML-1).

  keep     train on served volume as-is (biased low on stockout days)
  exclude  drop censored rows (biased toward agents that did not stock out)
  inflate  keep censored rows but raise their label to the agent's same-day P90 of uncensored peers
           of the same archetype (a simple imputation of the unseen demand)

Writes artifacts/censoring_experiment.json. Run: python scripts/censoring_experiment.py
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path

import numpy as np

from floatwise.config import get_config
from floatwise.data.generate import load_dataset
from floatwise.features.build import to_matrices
from floatwise.models.evaluate import coverage, evaluate_split, slice_masks, wape
from floatwise.models.predict import QuantileModels
from floatwise.models.train import split_panel, train


def main() -> None:
    base = get_config()
    cfg_dates = {
        "train_end": dt.date(2025, 2, 28),
        "val_start": dt.date(2025, 3, 1),
        "val_end": dt.date(2025, 6, 30),
    }
    data = load_dataset(base.data_dir)
    m = to_matrices(data["daily"])
    results = {}
    for mode in ("keep", "exclude", "inflate"):
        cfg = base.with_overrides(dates=cfg_dates, model={"censoring": mode})
        with tempfile.TemporaryDirectory() as tmp:
            train(cfg, data, Path(tmp), verbose=False)
            models = QuantileModels.load(cfg, Path(tmp))
            panel = split_panel(cfg, m, data, "val", sampled=False)
            masks = slice_masks(cfg, panel, m, data["calendar"], data["agents"])
            ev = evaluate_split(cfg, models, panel, masks)["cashout"]
            pred = models.predict_amount(panel, "cashout")
            y = panel["demand_cashout"].to_numpy()
            pre = (
                panel["days_to_eid_fitr"].between(1, 7) | panel["days_to_eid_adha"].between(1, 7)
            ).to_numpy()
            results[mode] = {
                "overall_wape": ev["overall"]["wape_model"],
                "event_wape": ev["event_days"]["wape_model"],
                "event_coverage": ev["event_days"]["coverage_p10_p90"],
                "pre_eid_wape": round(wape(y[pre], pred[pre, 1]), 4),
                "pre_eid_bias_p50": round(float((pred[pre, 1] - y[pre]).sum() / y[pre].sum()), 4),
                "pre_eid_above_p90": round(float(np.mean(y[pre] > pred[pre, 2])), 3),
                "pre_eid_coverage": round(coverage(y[pre], pred[pre, 0], pred[pre, 2]), 3),
            }
        print(mode, results[mode])
    best = min(results, key=lambda k: (results[k]["pre_eid_above_p90"], results[k]["event_wape"]))
    out = {
        "holdout": "2025-03-01 → 2025-06-30 (Eid-ul-Fitr and Eid-ul-Adha 2025)",
        "results": results,
        "selected": best,
        "criterion": "lowest share of pre-Eid demand above P90, then event WAPE",
    }
    (base.artifacts_dir / "censoring_experiment.json").write_text(json.dumps(out, indent=2))
    print("selected:", best)


if __name__ == "__main__":
    main()
