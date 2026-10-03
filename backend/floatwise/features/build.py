"""Leakage-safe origin/horizon feature panel (SRS §6.2, FR-FCST-3).

A row is (agent, origin t, horizon h) and predicts the target day d = t + h.
Rules (R-ML-2, R-ML-6):
  * history features use observed (served) data on days <= t only;
  * calendar features describe the target day d (known in advance);
  * ground-truth demand columns are never used as features — only as evaluation labels.
Targets are normalised by the agent's trailing 28-day mean at t, so one global model learns
multipliers ("x2.6 before Eid") that transfer across agents of very different size.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from floatwise.config import Config

SIDES = {"cashout": "cashout_amt", "cashin": "cashin_amt"}
DEMAND_COLS = {"cashout": "cashout_demand_amt", "cashin": "cashin_demand_amt"}
STOCKOUT_COLS = {"cashout": "stockout_cash", "cashin": "stockout_efloat"}
SCALE_FLOOR = 1000.0

CALENDAR_FEATURES = [
    "dow", "is_weekend", "day_of_month", "is_salary_window", "days_to_eid_fitr", "days_to_eid_adha",
    "days_after_eid", "is_ramadan", "is_boishakh", "is_public_holiday",
]  # fmt: skip
CATEGORICAL_FEATURES = ["archetype_code", "district_code"]


@dataclass
class Matrices:
    """Agent x date arrays of observed data plus lookups."""

    agent_ids: np.ndarray
    dates: pd.DatetimeIndex
    y: dict[str, np.ndarray]  # served amounts
    demand: dict[str, np.ndarray]  # ground truth (labels only)
    stockout: dict[str, np.ndarray]


def to_matrices(daily: pd.DataFrame) -> Matrices:
    d = daily.sort_values(["agent_id", "date"])
    agent_ids = d["agent_id"].unique()
    dates = pd.DatetimeIndex(np.sort(d["date"].unique()))
    shape = (len(agent_ids), len(dates))
    if len(d) != shape[0] * shape[1]:
        raise ValueError("daily panel must be complete (every agent x every date)")

    def mat(col: str) -> np.ndarray:
        return d[col].to_numpy(dtype=float).reshape(shape)

    return Matrices(
        agent_ids=agent_ids,
        dates=dates,
        y={s: mat(c) for s, c in SIDES.items()},
        demand={s: mat(c) for s, c in DEMAND_COLS.items()},
        stockout={s: mat(c) for s, c in STOCKOUT_COLS.items()},
    )


def _rolling(a: np.ndarray, window: int, fn: str) -> np.ndarray:
    """Trailing rolling statistic along the date axis (includes the current day)."""
    frame = pd.DataFrame(a.T)
    r = frame.rolling(window, min_periods=1)
    out = getattr(r, fn)()
    if fn == "std":
        out = out.fillna(0.0)
    return out.to_numpy().T


def _eid_memory(cfg: Config, m: Matrices, side: str, eids: list) -> np.ndarray:
    """(n_agents, n_dates): multiplier observed around the most recent Eid of one type that ended <= t."""
    y = m.y[side]
    out = np.full(y.shape, np.nan)
    day_pos = {d: i for i, d in enumerate(m.dates)}
    for eid in sorted(eids):
        e = day_pos.get(pd.Timestamp(eid))
        if e is None or e - 37 < 0:
            continue
        pre = y[:, e - 7 : e].mean(axis=1)
        base = np.maximum(y[:, e - 37 : e - 7].mean(axis=1), SCALE_FLOOR)
        out[:, e:] = (pre / base)[:, None]  # known from Eid day onward
    return out


def build_panel(
    cfg: Config,
    m: Matrices,
    calendar: pd.DataFrame,
    agents: pd.DataFrame,
    origin_idx: np.ndarray,
    horizons: np.ndarray | None = None,
    horizons_per_origin: int | None = None,
    rng: np.random.Generator | None = None,
    agent_idx: np.ndarray | None = None,
) -> pd.DataFrame:
    """Build feature rows for the given origin date indices.

    Either all `horizons` for every (agent, origin) or a random sample of `horizons_per_origin`.
    Rows whose target date falls past the data end keep NaN labels (pure forecasts).
    """
    n_a, n_d = m.y["cashout"].shape
    a_sel = np.arange(n_a) if agent_idx is None else np.asarray(agent_idx)
    H = cfg.model.horizons
    if horizons_per_origin is not None:
        assert rng is not None
        aa = np.repeat(a_sel, len(origin_idx) * horizons_per_origin)
        tt = np.tile(np.repeat(origin_idx, horizons_per_origin), len(a_sel))
        hh = rng.integers(1, H + 1, size=len(aa))
    else:
        hs = np.arange(1, H + 1) if horizons is None else np.asarray(horizons)
        aa = np.repeat(a_sel, len(origin_idx) * len(hs))
        tt = np.tile(np.repeat(origin_idx, len(hs)), len(a_sel))
        hh = np.tile(hs, len(a_sel) * len(origin_idx))
    dd = tt + hh
    in_range = dd < n_d
    dd_c = np.minimum(dd, n_d - 1)

    cal = calendar.set_index("date").reindex(m.dates)
    ag = agents.set_index("agent_id").reindex(m.agent_ids)
    arch_codes = {a: i for i, a in enumerate(cfg.archetypes)}
    dist_codes = {d: i for i, d in enumerate(sorted(cfg.network.districts))}

    f: dict[str, np.ndarray] = {"h": hh}
    for col in CALENDAR_FEATURES:
        f[col] = cal[col].to_numpy(dtype=float)[dd_c]
    f["archetype_code"] = ag["archetype"].map(arch_codes).to_numpy()[aa]
    f["district_code"] = ag["district"].map(dist_codes).to_numpy()[aa]

    scale = {}
    w = cfg.model.scale_window
    for side, y in m.y.items():
        p = "co" if side == "cashout" else "ci"
        m28 = np.maximum(_rolling(y, w, "mean"), SCALE_FLOOR)
        mean7 = _rolling(y, 7, "mean")
        std7 = _rolling(y, 7, "std")
        max28 = _rolling(y, w, "max")
        s = m28[aa, tt]
        scale[side] = s
        f[f"{p}_log_scale"] = np.log(s)
        f[f"{p}_lag0"] = y[aa, tt] / s
        f[f"{p}_lag1"] = y[aa, np.maximum(tt - 1, 0)] / s
        f[f"{p}_same_dow_7"] = y[aa, dd_c - 7] / s
        f[f"{p}_same_dow_14"] = y[aa, dd_c - 14] / s
        f[f"{p}_mean7"] = mean7[aa, tt] / s
        f[f"{p}_mean7_prev"] = mean7[aa, np.maximum(tt - 7, 0)] / s
        f[f"{p}_std7"] = std7[aa, tt] / s
        f[f"{p}_max28"] = max28[aa, tt] / s
        f[f"{p}_prev_fitr_mult"] = _eid_memory(cfg, m, side, cfg.calendar.eid_fitr)[aa, tt]
        f[f"{p}_prev_adha_mult"] = _eid_memory(cfg, m, side, cfg.calendar.eid_adha)[aa, tt]
        f[f"{p}_stockouts_7d"] = _rolling(m.stockout[side], 7, "sum")[aa, tt]

    cap = ag["float_capacity"].to_numpy(dtype=float)[aa]
    f["capacity_ratio"] = cap / (scale["cashout"] + scale["cashin"])
    f["ci_co_ratio"] = scale["cashin"] / scale["cashout"]

    panel = pd.DataFrame(f)
    panel.insert(0, "agent_idx", aa)
    panel.insert(1, "origin_idx", tt)
    panel.insert(2, "target_idx", dd)
    for side in SIDES:
        s = scale[side]
        y_t = np.where(in_range, m.y[side][aa, dd_c], np.nan)
        dem = np.where(in_range, m.demand[side][aa, dd_c], np.nan)
        cens = np.where(in_range, m.stockout[side][aa, dd_c], np.nan)
        panel[f"scale_{side}"] = s
        panel[f"label_{side}"] = y_t / s  # model target (observed, ratio)
        panel[f"demand_{side}"] = dem  # ground truth amount (evaluation only)
        panel[f"served_{side}"] = y_t
        panel[f"censored_{side}"] = cens
    return panel


def feature_columns(panel: pd.DataFrame) -> list[str]:
    meta = ("agent_idx", "origin_idx", "target_idx", "scale_", "label_", "demand_", "served_", "censored_")
    return [c for c in panel.columns if not c.startswith(meta)]


def origin_indices(m: Matrices, cfg: Config, first: pd.Timestamp, last: pd.Timestamp) -> np.ndarray:
    """Date indices of origins in [first, last] with enough history."""
    idx = np.where((m.dates >= first) & (m.dates <= last))[0]
    return idx[idx >= cfg.model.min_history_days]
