"""Per-forecast drivers via TreeSHAP (FR-XAI-1).

LightGBM's `pred_contrib=True` returns exact TreeSHAP values. Contributions are in the model's ratio
space (multiples of the agent's typical day), so multiplying by the agent's scale gives taka:
    forecast_P50 = scale x (base + sum(contributions)).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from floatwise.config import Config
from floatwise.explain import labels as L
from floatwise.models.predict import QuantileModels

PREFIX = {"cashout": "co", "cashin": "ci"}


def _display(cfg: Config, feature: str, value: float, lang: str) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    yes, no = ("হ্যাঁ", "না") if lang == "bn" else ("yes", "no")
    days = "দিন" if lang == "bn" else "days"
    if feature.startswith("days_to_eid") or feature == "days_after_eid":
        far = "অনেক দূরে" if lang == "bn" else "far away"
        return far if value >= 60 else f"{L.num(int(value), lang)} {days}"
    if feature.startswith("is_"):
        return yes if value >= 0.5 else no
    if feature == "dow":
        return L.DOW[lang][int(value)]
    if feature == "g2p_day_index":
        return "—" if value < 0 else f"{L.num(int(value) + 1, lang)}"
    if feature == "day_of_month":
        return L.num(int(value), lang)
    if feature == "h":
        return f"{L.num(int(value), lang)} {days}"
    if feature == "archetype_code":
        return L.ARCHETYPES[list(cfg.archetypes)[int(value)]][lang]
    if feature == "district_code":
        return sorted(cfg.network.districts)[int(value)]
    if feature.endswith("_log_scale"):
        return L.taka(math.exp(value), lang)
    if feature.endswith("_stockouts_7d"):
        return f"{L.num(int(value), lang)} {days}"
    return L.num(f"×{value:.2f}", lang)


def explain_row(
    cfg: Config, models: QuantileModels, row: pd.DataFrame, target: str, lang: str, top: int = 5
) -> dict:
    """Drivers of the P50 forecast for a single panel row."""
    booster = models.boosters[(target, 0.5)]
    x = row[models.features]
    contrib = booster.predict(x, pred_contrib=True, num_threads=models.inference_threads)[0]
    scale = float(row[f"scale_{target}"].iloc[0])
    phi = np.asarray(contrib[:-1]) * scale
    base = float(contrib[-1]) * scale
    order = np.argsort(-np.abs(phi))[:top]
    drivers = [
        {
            "feature": models.features[i],
            "label": L.feature_label(models.features[i], lang),
            "value": _display(cfg, models.features[i], float(x.iloc[0, i]), lang),
            "contribution_bdt": int(round(phi[i])),
        }
        for i in order
    ]
    return {
        "base_bdt": int(round(base)),
        "forecast_p50_bdt": int(round(base + phi.sum())),
        "drivers": drivers,
    }
