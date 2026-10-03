"""Choose the quantile architecture on a held-out Eid, never on the test period (R-ML-1).

  independent  one LightGBM per quantile
  spread       P50 + multiplicative spread models around an out-of-fold P50

Both arms are trained on data before 2025-03-01 and evaluated on 2025-03-01 → 2025-06-30, which holds
Eid-ul-Fitr and Eid-ul-Adha 2025. Writes artifacts/quantile_experiment.json.
Run: python scripts/quantile_experiment.py
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
from floatwise.models.evaluate import coverage, pinball, slice_masks, wape
from floatwise.models.predict import QuantileModels
from floatwise.models.train import split_panel, train


def main() -> None:
    base = get_config()
    dates = {
        "train_end": dt.date(2025, 2, 28),
        "val_start": dt.date(2025, 3, 1),
        "val_end": dt.date(2025, 6, 30),
    }
    data = load_dataset(base.data_dir)
    m = to_matrices(data["daily"])
    results = {}
    for mode in ("independent", "spread"):
        cfg = base.with_overrides(dates=dates, model={"quantile_mode": mode})
        with tempfile.TemporaryDirectory() as tmp:
            train(cfg, data, Path(tmp), verbose=False)
            models = QuantileModels.load(cfg, Path(tmp))
            panel = split_panel(cfg, m, data, "val", sampled=False)
            masks = slice_masks(cfg, panel, m, data["calendar"], data["agents"])
            res = {}
            for target in ("cashout", "cashin"):
                y = panel[f"demand_{target}"].to_numpy()
                pred = models.predict_amount(panel, target)
                x = panel[models.features]
                raw = {q: models.boosters[(target, q)].predict(x) for q in models.quantiles}
                if mode == "spread":
                    raw = {q: v if q == 0.5 else v * np.maximum(raw[0.5], 0.05) for q, v in raw.items()}
                crossing = float(np.mean((raw[0.1] > raw[0.5]) | (raw[0.5] > raw[0.9])))
                ev = masks["event_days"]
                res[target] = {
                    "wape_overall": round(wape(y, pred[:, 1]), 4),
                    "wape_event": round(wape(y[ev], pred[ev, 1]), 4),
                    "coverage_overall": round(coverage(y, pred[:, 0], pred[:, 2]), 3),
                    "coverage_event": round(coverage(y[ev], pred[ev, 0], pred[ev, 2]), 3),
                    "event_above_p90": round(float(np.mean(y[ev] > pred[ev, 2])), 3),
                    "mean_pinball_event": round(float(np.mean([pinball(y[ev], pred[ev, k], q)
                                                               for k, q in enumerate(models.quantiles)]))),
                    "raw_crossing_rate": round(crossing, 4),
                }  # fmt: skip
            results[mode] = res
        print(mode, json.dumps(results[mode]))

    # Adopt the more complex `spread` mode only if it lowers event pinball loss AND does not narrow
    # event-day P10-P90 coverage (narrower tails at Eid are the wrong direction for stockout prevention).
    ind, spr = results["independent"]["cashout"], results["spread"]["cashout"]
    adopt = (
        spr["mean_pinball_event"] < ind["mean_pinball_event"]
        and spr["coverage_event"] >= ind["coverage_event"]
    )
    best = "spread" if adopt else "independent"
    out = {
        "holdout": "2025-03-01 → 2025-06-30 (Eid-ul-Fitr and Eid-ul-Adha 2025), trained on data before it",
        "criterion": "adopt spread only if cash-out event pinball improves AND event P10-P90 coverage does not drop",
        "results": results,
        "selected": best,
    }
    (base.artifacts_dir / "quantile_experiment.json").write_text(json.dumps(out, indent=2))
    print("selected:", best)


if __name__ == "__main__":
    main()
