"""Capacity-constrained DSO visit plan (SRS §7.3, FR-ALLOC-1..4): greedy by taka at risk, or exact."""

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


CASH_UNIT = 1000  # cash needs are rounded up to whole ৳1,000 for the exact solver


def plan_dso_optimal(
    action: np.ndarray, cash_delta: np.ndarray, priority: np.ndarray, max_visits: int, max_cash: int
) -> Plan:
    """Exact visit plan (FR-ALLOC-4): maximise total taka at risk covered subject to the visit limit and
    the cash bag — a two-constraint 0/1 knapsack solved by dynamic programming over (visits, cash).
    Visits are returned in priority order; same Plan shape as the greedy planner. Never worse than greedy."""
    cand = [int(i) for i in np.argsort(-priority, kind="stable") if action[i] != NO_ACTION]
    need = {i: max(int(np.ceil(max(cash_delta[i], 0.0) / CASH_UNIT)), 0) for i in cand}
    cap = min(int(max_cash // CASH_UNIT), sum(need.values()))
    k_max = min(max_visits, len(cand))
    neg = -np.inf
    dp = np.full((k_max + 1, cap + 1), neg)
    dp[0, :] = 0.0  # dp[k, m] = best value with k visits and cash use <= m
    take = np.zeros((len(cand), k_max + 1, cap + 1), dtype=bool)
    for j, i in enumerate(cand):
        w, v = need[i], float(priority[i])
        if w > cap:
            continue
        for k in range(k_max, 0, -1):
            prev = dp[k - 1, : cap + 1 - w] + v
            cur = dp[k, w:]
            better = prev > cur
            cur[better] = prev[better]
            take[j, k, w:] |= better
    # best (k, m): any k, full cash budget
    k_best = int(np.argmax(dp[:, cap]))
    chosen: list[int] = []
    k, m = k_best, cap
    for j in range(len(cand) - 1, -1, -1):
        if k > 0 and take[j, k, m]:
            chosen.append(cand[j])
            m -= need[cand[j]]
            k -= 1
    chosen_set = set(chosen)
    visits = [i for i in cand if i in chosen_set]
    excluded = []
    for i in cand:
        if i in chosen_set:
            continue
        reason = "visit limit reached" if len(visits) >= max_visits else "cash bag full"
        excluded.append((i, f"{reason} — self-rebalance at distributor point"))
    bag = sum(max(int(round(cash_delta[i])), 0) for i in visits)
    efl = sum(max(-int(round(cash_delta[i])), 0) for i in visits)
    exact = Plan(visits, excluded, bag, efl)
    # cash is rounded up to ৳1,000 units, so the DP can be a hair conservative; never return less than greedy
    greedy = plan_dso(action, cash_delta, priority, max_visits, max_cash)
    return exact if priority[exact.visits].sum() >= priority[greedy.visits].sum() else greedy


PLANNERS = {"greedy": plan_dso, "optimal": plan_dso_optimal}
