"""Capacity-constrained DSO visit plan (SRS §7.3, FR-ALLOC-1..3). Greedy by taka at risk."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from floatwise.engine.recommend import NO_ACTION


@dataclass
class Plan:
    visits: list[int]  # positions (into the candidate arrays), in visiting order
    excluded: list[tuple[int, str]]  # (position, reason)
    cash_to_carry: int
    efloat_to_send: int


def plan_dso(
    action: np.ndarray, cash_delta: np.ndarray, priority: np.ndarray, max_visits: int, max_cash: int
) -> Plan:
    """Pick agents to visit for one DSO.

    action/cash_delta/priority are arrays for the DSO's agents. A visit that delivers cash
    (cash_delta > 0) consumes the cash bag; converting cash to e-float does not.
    Highest expected shortfall first; an agent whose cash does not fit is skipped, not the rest.
    """
    candidates = [i for i in np.argsort(-priority, kind="stable") if action[i] != NO_ACTION]
    visits: list[int] = []
    excluded: list[tuple[int, str]] = []
    bag = 0
    efloat = 0
    for i in candidates:
        need = max(int(round(cash_delta[i])), 0)
        if len(visits) >= max_visits:
            excluded.append((int(i), "visit limit reached — self-rebalance at distributor point"))
        elif bag + need > max_cash:
            excluded.append((int(i), "cash bag full — self-rebalance at distributor point"))
        else:
            visits.append(int(i))
            bag += need
            efloat += max(-int(round(cash_delta[i])), 0)
    return Plan(visits, excluded, bag, efloat)
