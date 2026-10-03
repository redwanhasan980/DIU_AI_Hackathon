"""Rebalancing recommendation (SRS §7.2) — the only place money amounts are decided (R-AI-1).

Vectorised over agents. Inputs are next-day quantile forecasts and the agent's balances at close.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from floatwise.config import Config
from floatwise.engine import risk

TOP_UP_CASH = "TOP_UP_CASH"
TOP_UP_EFLOAT = "TOP_UP_EFLOAT"
NO_ACTION = "NO_ACTION"
NEEDS_EXTRA_FLOAT = "NEEDS_EXTRA_FLOAT"


@dataclass(frozen=True)
class PolicyParams:
    service_level: float
    risk_threshold: float
    overlap_alpha: float
    min_buffer_cash: int
    min_buffer_efloat: int
    round_to: int

    @classmethod
    def from_config(cls, cfg: Config, **overrides: float | None) -> PolicyParams:
        fw = cfg.policy.floatwise
        base = cls(fw.service_level, fw.risk_threshold, fw.overlap_alpha, fw.min_buffer_cash,
                   fw.min_buffer_efloat, fw.round_to)  # fmt: skip
        return replace(base, **{k: v for k, v in overrides.items() if v is not None})


def round_up(x: np.ndarray, step: int) -> np.ndarray:
    return (np.ceil(np.asarray(x, dtype=float) / step) * step).astype(np.int64)


def recommend(
    params: PolicyParams,
    open_cash: np.ndarray,
    open_efloat: np.ndarray,
    capacity: np.ndarray,
    co_q: np.ndarray,
    ci_q: np.ndarray,
) -> dict[str, np.ndarray]:
    """Return per-agent action, amount, targets, probabilities and the resulting cash level.

    co_q / ci_q: (n, 3) next-day P10/P50/P90 forecasts of cash-out / cash-in demand.
    """
    p = params
    open_cash = np.asarray(open_cash, dtype=float)
    open_efloat = np.asarray(open_efloat, dtype=float)
    capacity = np.asarray(capacity, dtype=float)
    co50, ci50 = co_q[:, 1], ci_q[:, 1]

    # same-day inflows partly fund outflows (overlap factor alpha)
    avail_cash = open_cash + p.overlap_alpha * ci50
    avail_efloat = open_efloat + p.overlap_alpha * co50
    p_cash = risk.stockout_probability(avail_cash, co_q)
    p_efloat = risk.stockout_probability(avail_efloat, ci_q)

    target_cash = (
        np.maximum(risk.quantile(p.service_level, co_q) - p.overlap_alpha * ci50, 0) + p.min_buffer_cash
    )
    target_efloat = (
        np.maximum(risk.quantile(p.service_level, ci_q) - p.overlap_alpha * co50, 0) + p.min_buffer_efloat
    )
    target_cash = round_up(target_cash, p.round_to)
    target_efloat = round_up(target_efloat, p.round_to)

    cash_gap = target_cash - open_cash
    efloat_gap = target_efloat - open_efloat
    cash_risky = p_cash >= p.risk_threshold
    efloat_risky = p_efloat >= p.risk_threshold
    short_capacity = target_cash + target_efloat > capacity

    n = len(open_cash)
    action = np.full(n, NO_ACTION, dtype=object)
    amount = np.zeros(n, dtype=np.int64)
    new_cash = open_cash.copy()

    extra = short_capacity & (cash_risky | efloat_risky)
    top_cash = ~extra & (cash_gap > 0) & cash_risky
    top_efloat = ~extra & ~top_cash & (efloat_gap > 0) & efloat_risky

    amt_cash = round_up(np.maximum(cash_gap, 0), p.round_to)
    amt_efloat = round_up(np.maximum(efloat_gap, 0), p.round_to)
    action[top_cash] = TOP_UP_CASH
    amount[top_cash] = amt_cash[top_cash]
    new_cash[top_cash] = np.minimum(open_cash + amt_cash, capacity)[top_cash]
    action[top_efloat] = TOP_UP_EFLOAT
    amount[top_efloat] = amt_efloat[top_efloat]
    new_cash[top_efloat] = np.maximum(open_cash - amt_efloat, 0)[top_efloat]

    # capacity cannot cover both needs: escalate to a human, and split the float pro rata as a best effort
    shortfall_float = np.maximum(target_cash + target_efloat - capacity, 0)
    split_cash = np.round(capacity * target_cash / np.maximum(target_cash + target_efloat, 1), -3)
    action[extra] = NEEDS_EXTRA_FLOAT
    amount[extra] = round_up(shortfall_float, p.round_to)[extra]
    new_cash[extra] = np.clip(split_cash, 0, capacity)[extra]

    es_cash = risk.expected_shortfall(avail_cash, co_q)
    es_efloat = risk.expected_shortfall(avail_efloat, ci_q)
    return {
        "action": action,
        "amount": amount,
        "new_cash": new_cash,
        "cash_delta": new_cash - open_cash,  # + cash delivered to the agent, - cash collected
        "target_cash": target_cash,
        "target_efloat": target_efloat,
        "p_cash_stockout": p_cash,
        "p_efloat_stockout": p_efloat,
        "p_stockout": np.maximum(p_cash, p_efloat),
        "extra_float_needed": round_up(shortfall_float, p.round_to),
        "expected_shortfall": np.maximum(es_cash, es_efloat),  # taka at risk if nothing is done
    }


def risk_band(p_stockout: np.ndarray, threshold: float) -> np.ndarray:
    """low < threshold <= medium < 0.3 <= high."""
    p = np.asarray(p_stockout)
    return np.where(p >= 0.3, "high", np.where(p >= threshold, "medium", "low"))


def reason_codes(
    cal_row: pd.Series, rec: dict, i: int, params: PolicyParams, recent_stockouts: int
) -> list[str]:
    """Machine-readable reasons for one agent (FR-REC-3). `cal_row` describes the effective date."""
    codes = []
    if 1 <= cal_row["days_to_eid_fitr"] <= 10:
        codes.append(f"EID_FITR_IN_{int(cal_row['days_to_eid_fitr'])}_DAYS")
    if 1 <= cal_row["days_to_eid_adha"] <= 10:
        codes.append(f"EID_ADHA_IN_{int(cal_row['days_to_eid_adha'])}_DAYS")
    if cal_row["is_eid_fitr"] or cal_row["is_eid_adha"]:
        codes.append("EID_DAY")
    elif cal_row["days_after_eid"] < 3:
        codes.append("EID_HOLIDAY")
    if cal_row["is_salary_window"]:
        codes.append("SALARY_WINDOW")
    if cal_row["is_ramadan"]:
        codes.append("RAMADAN")
    if cal_row["is_boishakh"]:
        codes.append("POHELA_BOISHAKH")
    if rec["p_cash_stockout"][i] >= params.risk_threshold:
        codes.append("CASH_BELOW_NEED")
    if rec["p_efloat_stockout"][i] >= params.risk_threshold:
        codes.append("EFLOAT_BELOW_NEED")
    if rec["action"][i] == NEEDS_EXTRA_FLOAT:
        codes.append("FLOAT_CAPACITY_SHORT")
    if recent_stockouts > 0:
        codes.append("RECENT_STOCKOUTS")
    return codes
