"""Normalised conformal interval expansion by known event status and horizon.

Fit only on observations from a separate calibration period. Censored observations
must be excluded: served volume cannot stand in for latent demand on stockout days.
Temporal and distribution shifts can invalidate exchangeability; coverage is measured,
never guaranteed. This calibrator is an experiment until separately validated.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def event_mask(panel: pd.DataFrame, window: tuple[int, int]) -> np.ndarray:
    return (
        (panel["days_to_eid_fitr"].to_numpy() <= -window[0])
        | (panel["days_to_eid_adha"].to_numpy() <= -window[0])
        | (panel["days_after_eid"].to_numpy() <= window[1])
    )


@dataclass
class IntervalCalibrator:
    adjustments: dict[str, dict]
    window: tuple[int, int]

    @classmethod
    def fit(
        cls,
        panel: pd.DataFrame,
        predictions: dict[str, np.ndarray],
        window: tuple[int, int],
        target_coverage: float,
        min_rows: int,
    ) -> IntervalCalibrator:
        events = event_mask(panel, window)
        adjustments = {}
        for target, pred in predictions.items():
            y = panel[f"served_{target}"].to_numpy()
            valid = np.isfinite(y) & (panel[f"censored_{target}"].to_numpy() == 0)
            scores = np.maximum(pred[:, 0] - y, y - pred[:, 2]) / panel[f"scale_{target}"].to_numpy()
            for event in (False, True):
                for h in sorted(panel["h"].unique()):
                    mask = valid & (events == event) & (panel["h"].to_numpy() == h)
                    pooled = False
                    if mask.sum() < min_rows:
                        mask = valid & (events == event)
                        pooled = True
                    n = int(mask.sum())
                    if n < min_rows:
                        adjustments[f"{target}:{int(event)}:{h}"] = {
                            "expansion": 0.0,
                            "n": n,
                            "supported": False,
                            "pooled_horizons": pooled,
                        }
                        continue
                    # Finite sample conformal rank. Only expansion, never shrink the raw interval.
                    rank = min(int(np.ceil((n + 1) * target_coverage)), n)
                    expansion = max(float(np.partition(scores[mask], rank - 1)[rank - 1]), 0.0)
                    adjustments[f"{target}:{int(event)}:{h}"] = {
                        "expansion": expansion,
                        "n": n,
                        "supported": True,
                        "pooled_horizons": pooled,
                    }
        return cls(adjustments, window)

    def apply(self, panel: pd.DataFrame, pred: np.ndarray, target: str) -> np.ndarray:
        events = event_mask(panel, self.window)
        amounts = (
            np.array(
                [
                    self.adjustments[f"{target}:{int(e)}:{h}"]["expansion"]
                    for e, h in zip(events, panel["h"], strict=True)
                ]
            )
            * panel[f"scale_{target}"].to_numpy()
        )
        out = pred.copy()
        out[:, 0] = np.maximum(0, out[:, 0] - amounts)
        out[:, 2] += amounts
        return out
