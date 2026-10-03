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
    escalation_service_level: float

    @classmethod
    def from_config(cls, cfg: Config, **overrides: float | None) -> PolicyParams:
        fw = cfg.policy.floatwise
        base = cls(fw.service_level, fw.risk_threshold, fw.overlap_alpha, fw.min_buffer_cash,
                   fw.min_buffer_efloat, fw.round_to, fw.escalation_service_level)  # fmt: skip
        return replace(base, **{k: v for k, v in overrides.items() if v is not None})


def round_up(x: np.ndarray, step: int) -> np.ndarray:
    return (np.ceil(np.asarray(x, dtype=float) / step) * step).astype(np.int64)


def _targets(
    p: PolicyParams, level: float, co_q: np.ndarray, ci_q: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Balances that cover next-day demand with probability `level` (same-day inflows count at alpha)."""
    co50, ci50 = co_q[:, 1], ci_q[:, 1]
    cash = np.maximum(risk.quantile(level, co_q) - p.overlap_alpha * ci50, 0) + p.min_buffer_cash
    efloat = np.maximum(risk.quantile(level, ci_q) - p.overlap_alpha * co50, 0) + p.min_buffer_efloat
    return round_up(cash, p.round_to), round_up(efloat, p.round_to)


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
    Rebalancing converts between cash and e-float, so total float (capacity) is fixed:
      * both targets fit      -> move the risky side to its target;
      * they do not fit       -> best split of the float, pro rata to the two targets;
      * even the P90-level needs (escalation_service_level) do not fit -> NEEDS_EXTRA_FLOAT, a human
        decides on extra float; the best split is still suggested.
    """
    p = params
    open_cash = np.asarray(open_cash, dtype=float)
    open_efloat = np.asarray(open_efloat, dtype=float)
    capacity = np.asarray(capacity, dtype=float)

    avail_cash = open_cash + p.overlap_alpha * ci_q[:, 1]
    avail_efloat = open_efloat + p.overlap_alpha * co_q[:, 1]
    p_cash = risk.stockout_probability(avail_cash, co_q)
    p_efloat = risk.stockout_probability(avail_efloat, ci_q)
    cash_risky = p_cash >= p.risk_threshold
    efloat_risky = p_efloat >= p.risk_threshold
    risky = cash_risky | efloat_risky

    target_cash, target_efloat = _targets(p, p.service_level, co_q, ci_q)
    min_cash, min_efloat = _targets(p, p.escalation_service_level, co_q, ci_q)
    fits = target_cash + target_efloat <= capacity
    split = np.clip(
        np.round(capacity * target_cash / np.maximum(target_cash + target_efloat, 1), -3), 0, capacity
    )

    desired = open_cash.copy()
    up_cash = fits & cash_risky & (target_cash > open_cash)
    up_efloat = fits & ~up_cash & efloat_risky & (target_efloat > open_efloat)
    desired[up_cash] = target_cash[up_cash]
    desired[up_efloat] = (open_cash - (target_efloat - open_efloat))[up_efloat]
    desired[~fits & risky] = split[~fits & risky]

    delta = desired - open_cash
    amount = round_up(np.abs(delta), p.round_to)
    amount[np.abs(delta) < 1] = 0
    action = np.full(len(open_cash), NO_ACTION, dtype=object)
    action[(delta > 0) & (amount > 0)] = TOP_UP_CASH
    action[(delta < 0) & (amount > 0)] = TOP_UP_EFLOAT
    new_cash = np.clip(open_cash + np.sign(delta) * amount, 0, capacity)

    extra_needed = round_up(np.maximum(min_cash + min_efloat - capacity, 0), p.round_to)
    escalate = risky & (extra_needed > 0)
    action[escalate] = NEEDS_EXTRA_FLOAT
    amount[escalate] = extra_needed[escalate]

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
        "extra_float_needed": extra_needed,
        "expected_shortfall": np.maximum(es_cash, es_efloat),  # taka at risk if nothing is done
    }


def risk_band(p_stockout: np.ndarray, threshold: float) -> np.ndarray:
    """low < threshold <= medium < 0.5 <= high (a stockout is more likely than not)."""
    p = np.asarray(p_stockout)
    return np.where(p >= 0.5, "high", np.where(p >= threshold, "medium", "low"))


def reason_codes(
    today: pd.Series, effective: pd.Series, rec: dict, i: int, params: PolicyParams, recent_stockouts: int
) -> list[str]:
    """Machine-readable reasons for one agent (FR-REC-3).

    Event countdowns are counted from the decision date (`today`); day types (salary, Ramadan, Eid
    holiday) describe the day the rebalance protects (`effective`).
    """
    codes = []
    for col, name in (("days_to_eid_fitr", "EID_FITR"), ("days_to_eid_adha", "EID_ADHA")):
        if 1 <= today[col] <= 10:
            codes.append(f"{name}_IN_{int(today[col])}_DAYS")
    if effective["is_eid_fitr"] or effective["is_eid_adha"]:
        codes.append("EID_DAY")
    elif effective["days_after_eid"] < 3:
        codes.append("EID_HOLIDAY")
    if effective["is_salary_window"]:
        codes.append("SALARY_WINDOW")
    if effective["is_ramadan"]:
        codes.append("RAMADAN")
    if effective["is_boishakh"]:
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
