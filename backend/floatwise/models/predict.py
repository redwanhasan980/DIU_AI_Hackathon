"""Load trained quantile models and predict amounts (non-crossing, R-ML-4)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from floatwise.config import Config

SPREAD_FLOOR = 0.05  # minimum median ratio used as the base of spread quantiles


def model_path(models_dir: Path, target: str, q: float) -> Path:
    return models_dir / f"{target}_q{int(round(q * 100)):02d}.txt"


@dataclass
class QuantileModels:
    boosters: dict[tuple[str, float], lgb.Booster]
    features: list[str]
    quantiles: list[float]
    targets: list[str]
    version: str
    mode: str = "independent"

    @classmethod
    def load(cls, cfg: Config, models_dir: Path | None = None) -> QuantileModels:
        models_dir = models_dir or cfg.models_dir
        meta = json.loads((models_dir / "meta.json").read_text())
        boosters = {
            (t, q): lgb.Booster(model_file=str(model_path(models_dir, t, q)))
            for t in meta["targets"]
            for q in meta["quantiles"]
        }
        return cls(boosters, meta["features"], meta["quantiles"], meta["targets"], meta["version"],
                   meta.get("quantile_mode", "independent"))  # fmt: skip

    def predict_ratio(self, panel: pd.DataFrame, target: str) -> np.ndarray:
        """(n_rows, n_quantiles) predicted ratios to the trailing scale, sorted to be non-crossing."""
        x = panel[self.features]
        raw = {q: self.boosters[(target, q)].predict(x) for q in self.quantiles}
        if self.mode == "spread":
            base = np.maximum(raw[0.5], SPREAD_FLOOR)
            raw = {q: (v if q == 0.5 else v * base) for q, v in raw.items()}
        preds = np.column_stack([raw[q] for q in self.quantiles])
        return np.sort(preds, axis=1)  # rearrangement: enforce P10 <= P50 <= P90 (R-ML-4)

    def predict_amount(self, panel: pd.DataFrame, target: str) -> np.ndarray:
        ratio = self.predict_ratio(panel, target)
        ratio = np.maximum(ratio, 0.0)
        return ratio * panel[f"scale_{target}"].to_numpy()[:, None]
