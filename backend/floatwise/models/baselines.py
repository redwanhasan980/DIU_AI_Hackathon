"""Baselines every model must beat (FR-FCST-1, R-ML-3). Work on the feature panel."""

from __future__ import annotations

import numpy as np
import pandas as pd

PREFIX = {"cashout": "co", "cashin": "ci"}


def seasonal_naive(panel: pd.DataFrame, target: str) -> np.ndarray:
    """Same weekday last week: y(d - 7)."""
    p = PREFIX[target]
    return panel[f"{p}_same_dow_7"].to_numpy() * panel[f"scale_{target}"].to_numpy()


def trailing_mean7(panel: pd.DataFrame, target: str) -> np.ndarray:
    """Mean of the last 7 observed days at the origin."""
    p = PREFIX[target]
    return panel[f"{p}_mean7"].to_numpy() * panel[f"scale_{target}"].to_numpy()


BASELINES = {"seasonal_naive": seasonal_naive, "trailing_mean7": trailing_mean7}
