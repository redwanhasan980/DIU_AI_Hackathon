"""Agent ledger mechanics and the status-quo rebalancing rule (FR-DATA-4).

Total float (cash + e-float) is conserved: a cash-out moves value from cash to e-float, a cash-in the
reverse, and rebalancing only converts between the two. The intraday order of transactions matters,
so each day is simulated in a few slots (cash-outs skew to the morning, cash-ins to the evening).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from floatwise.config import Config, StatusQuoPolicy


@dataclass
class DayResult:
    cash: np.ndarray
    efloat: np.ndarray
    served_co: np.ndarray
    served_ci: np.ndarray


def serve_day(
    cash: np.ndarray,
    efloat: np.ndarray,
    co_demand: np.ndarray,
    ci_demand: np.ndarray,
    co_profile: list[float],
    ci_profile: list[float],
) -> DayResult:
    """Serve one day of demand for all agents (vectorised). Cash-outs are served first in each slot."""
    cash = cash.astype(float).copy()
    efloat = efloat.astype(float).copy()
    served_co = np.zeros_like(cash)
    served_ci = np.zeros_like(cash)
    for p_co, p_ci in zip(co_profile, ci_profile, strict=True):
        s_co = np.minimum(co_demand * p_co, cash)
        cash -= s_co
        efloat += s_co
        served_co += s_co
        s_ci = np.minimum(ci_demand * p_ci, efloat)
        efloat -= s_ci
        cash += s_ci
        served_ci += s_ci
    return DayResult(cash, efloat, served_co, served_ci)


def status_quo_next_cash(
    policy: StatusQuoPolicy,
    hist_co: np.ndarray,
    hist_ci: np.ndarray,
    close_cash: np.ndarray,
    close_efloat: np.ndarray,
    capacity: np.ndarray,
) -> np.ndarray:
    """Today's rule of thumb: keep `target_ratio` x trailing mean volume; rebalance below `trigger_ratio`.

    hist_* are (n_agents, k) arrays of recent *served* volumes (what the agent can observe).
    Returns the cash level for the next morning (e-float = capacity - cash).
    """
    target_cash = policy.target_ratio * hist_co.mean(axis=1)
    target_efloat = policy.target_ratio * hist_ci.mean(axis=1)
    new_cash = close_cash.astype(float).copy()

    low_cash = close_cash < policy.trigger_ratio * target_cash
    low_efloat = ~low_cash & (close_efloat < policy.trigger_ratio * target_efloat)
    new_cash[low_cash] = np.minimum(np.round(target_cash[low_cash], -3), capacity[low_cash])
    new_cash[low_efloat] = capacity[low_efloat] - np.minimum(
        np.round(target_efloat[low_efloat], -3), capacity[low_efloat]
    )
    return np.clip(new_cash, 0, capacity)


def simulate_status_quo(
    cfg: Config, agents: pd.DataFrame, calendar: pd.DataFrame, demand: dict[str, np.ndarray]
) -> dict[str, np.ndarray]:
    """Run the whole period under the status-quo policy. Returns (n_agents, n_dates) arrays."""
    n_a, n_d = demand["co_demand"].shape
    capacity = agents["float_capacity"].to_numpy(dtype=float)
    cash = agents["opening_cash"].to_numpy(dtype=float)
    efloat = capacity - cash
    look = cfg.policy.status_quo.lookback_days

    out = {
        k: np.zeros((n_a, n_d))
        for k in (
            "open_cash",
            "open_efloat",
            "close_cash",
            "close_efloat",
            "served_co",
            "served_ci",
            "rebalance_cash",
        )
    }
    for d in range(n_d):
        out["open_cash"][:, d] = cash
        out["open_efloat"][:, d] = efloat
        res = serve_day(
            cash,
            efloat,
            demand["co_demand"][:, d],
            demand["ci_demand"][:, d],
            cfg.demand.co_slot_profile,
            cfg.demand.ci_slot_profile,
        )
        out["served_co"][:, d] = res.served_co
        out["served_ci"][:, d] = res.served_ci
        out["close_cash"][:, d] = res.cash
        out["close_efloat"][:, d] = res.efloat

        lo = max(0, d - look + 1)
        new_cash = status_quo_next_cash(
            cfg.policy.status_quo,
            out["served_co"][:, lo : d + 1],
            out["served_ci"][:, lo : d + 1],
            res.cash,
            res.efloat,
            capacity,
        )
        if d + 1 < n_d:
            out["rebalance_cash"][:, d + 1] = new_cash - res.cash
        cash, efloat = new_cash, capacity - new_cash
    return out
