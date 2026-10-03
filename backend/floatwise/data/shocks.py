"""Random local shocks — floods, network outages, hartals (FR-DATA-5). Logged as ground truth."""

from __future__ import annotations

import numpy as np
import pandas as pd

from floatwise.config import Config


def build_shocks(cfg: Config, calendar: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    all_districts = sorted(cfg.network.districts)
    type_names = sorted(cfg.shocks.types)
    rows = []
    for i in range(cfg.shocks.n_shocks):
        name = type_names[i % len(type_names)]
        spec = cfg.shocks.types[name]
        candidates = calendar.loc[calendar["month"].isin(spec.months), "date"].to_numpy()
        if len(candidates) == 0:  # shock season outside the simulated range
            continue
        start = pd.Timestamp(rng.choice(candidates))
        days = int(rng.integers(spec.min_days, spec.max_days + 1))
        districts = all_districts if spec.districts == "all" else list(spec.districts)
        rows.append(
            {
                "shock_id": f"SH{i + 1:03d}",
                "type": name,
                "district": str(rng.choice(districts)),
                "start_date": start,
                "end_date": start + pd.Timedelta(days=days - 1),
                "multiplier": spec.mult,
            }
        )
    cols = ["shock_id", "type", "district", "start_date", "end_date", "multiplier"]
    return pd.DataFrame(rows, columns=cols).sort_values("start_date").reset_index(drop=True)


def shock_matrix(shocks: pd.DataFrame, districts: list[str], dates: pd.DatetimeIndex) -> np.ndarray:
    """(n_districts, n_dates) multiplier matrix; 1.0 where no shock is active."""
    mat = np.ones((len(districts), len(dates)))
    pos = {d: i for i, d in enumerate(districts)}
    for s in shocks.itertuples():
        if s.district not in pos:
            continue
        mask = (dates >= s.start_date) & (dates <= s.end_date)
        mat[pos[s.district], mask] *= s.multiplier
    return mat
