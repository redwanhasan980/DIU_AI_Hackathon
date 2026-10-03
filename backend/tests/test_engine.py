"""Decision engine: risk maths, recommendations and DSO allocation (R-CODE-4)."""

from __future__ import annotations

import numpy as np
import pytest

from floatwise.engine import risk
from floatwise.engine.allocate import plan_dso
from floatwise.engine.recommend import (
    NEEDS_EXTRA_FLOAT,
    NO_ACTION,
    TOP_UP_CASH,
    TOP_UP_EFLOAT,
    PolicyParams,
    recommend,
    risk_band,
)

Q = np.array([[80_000.0, 100_000.0, 130_000.0]])


# ---- risk -------------------------------------------------------------------


def test_cdf_hits_the_quantiles():
    np.testing.assert_allclose(
        risk.cdf(np.array([80_000, 100_000, 130_000]), np.repeat(Q, 3, 0)), [0.1, 0.5, 0.9], atol=1e-6
    )


def test_stockout_probability_is_monotone_and_bounded():
    bal = np.linspace(0, 300_000, 50)
    p = risk.stockout_probability(bal, np.repeat(Q, 50, 0))
    assert (np.diff(p) <= 1e-12).all() and p[0] == pytest.approx(1.0) and p[-1] == 0.0


def test_quantile_inverts_cdf():
    for level in (0.1, 0.5, 0.8, 0.9, 0.95, 0.99):
        x = risk.quantile(level, Q)
        assert risk.cdf(x, Q)[0] == pytest.approx(level, abs=1e-6)


def test_expected_shortfall_matches_monte_carlo():
    rng = np.random.default_rng(0)
    k = risk.knots(Q)[0]
    u = rng.uniform(0, 1, 400_000)
    draws = np.interp(u, risk.PROBS, k)  # sample from the piecewise-linear distribution
    for a in (50_000.0, 100_000.0, 150_000.0):
        mc = np.maximum(draws - a, 0).mean()
        assert risk.expected_shortfall(np.array([a]), Q)[0] == pytest.approx(mc, rel=0.02)


def test_collapsed_quantiles_do_not_crash():
    q = np.array([[0.0, 0.0, 0.0], [5.0, 5.0, 5.0]])
    p = risk.stockout_probability(np.array([0.0, 10.0]), q)
    assert np.isfinite(p).all()


# ---- recommend --------------------------------------------------------------


@pytest.fixture
def params(cfg):
    return PolicyParams.from_config(cfg)


def _rec(params, cash, efloat, cap, co, ci):
    return recommend(
        params,
        np.array([cash], float),
        np.array([efloat], float),
        np.array([cap], float),
        np.array([co], float),
        np.array([ci], float),
    )


def test_low_cash_before_eid_tops_up_cash(params):
    # Eid spike: cash-out P90 2.6 lakh, agent holds 50k cash, plenty of e-float
    r = _rec(params, 50_000, 450_000, 500_000, [150_000, 200_000, 260_000], [20_000, 30_000, 40_000])
    assert r["action"][0] == TOP_UP_CASH
    assert r["amount"][0] % params.round_to == 0
    assert r["new_cash"][0] == 50_000 + r["amount"][0]
    assert r["p_cash_stockout"][0] > 0.5


def test_comfortable_balance_needs_no_action(params):
    r = _rec(params, 300_000, 300_000, 600_000, [80_000, 100_000, 130_000], [80_000, 100_000, 130_000])
    assert r["action"][0] == NO_ACTION and r["amount"][0] == 0
    assert r["p_stockout"][0] < params.risk_threshold


def test_low_efloat_tops_up_efloat(params):
    r = _rec(params, 550_000, 20_000, 570_000, [30_000, 40_000, 50_000], [200_000, 300_000, 400_000])
    assert r["action"][0] == TOP_UP_EFLOAT
    assert r["new_cash"][0] == 550_000 - r["amount"][0]


def test_insufficient_capacity_escalates(params):
    r = _rec(params, 100_000, 100_000, 200_000, [200_000, 300_000, 400_000], [200_000, 300_000, 400_000])
    assert r["action"][0] == NEEDS_EXTRA_FLOAT
    assert r["extra_float_needed"][0] > 0
    assert 0 <= r["new_cash"][0] <= 200_000


def test_higher_service_level_means_higher_target(cfg):
    lo = PolicyParams.from_config(cfg, service_level=0.8)
    hi = PolicyParams.from_config(cfg, service_level=0.98)
    args = (50_000, 450_000, 900_000, [150_000, 200_000, 260_000], [20_000, 30_000, 40_000])
    assert _rec(hi, *args)["target_cash"][0] > _rec(lo, *args)["target_cash"][0]


def test_recommend_is_deterministic(params):
    args = (50_000, 450_000, 500_000, [150_000, 200_000, 260_000], [20_000, 30_000, 40_000])
    a, b = _rec(params, *args), _rec(params, *args)
    assert a["amount"][0] == b["amount"][0] and a["action"][0] == b["action"][0]


def test_risk_band():
    assert list(risk_band(np.array([0.05, 0.2, 0.5]), 0.1)) == ["low", "medium", "high"]


# ---- allocate ---------------------------------------------------------------


def test_plan_respects_visit_and_cash_limits():
    n = 20
    action = np.array([TOP_UP_CASH] * n, dtype=object)
    cash_delta = np.full(n, 150_000.0)
    priority = np.arange(n, dtype=float)
    plan = plan_dso(action, cash_delta, priority, max_visits=10, max_cash=1_000_000)
    assert len(plan.visits) <= 10 and plan.cash_to_carry <= 1_000_000
    assert plan.visits[0] == n - 1  # highest priority first
    assert len(plan.visits) + len(plan.excluded) == n


def test_plan_skips_big_cash_but_keeps_smaller_ones():
    action = np.array([TOP_UP_CASH, TOP_UP_CASH, TOP_UP_EFLOAT, NO_ACTION], dtype=object)
    cash_delta = np.array([900_000.0, 50_000.0, -200_000.0, 0.0])
    priority = np.array([10.0, 5.0, 8.0, 99.0])
    plan = plan_dso(action, cash_delta, priority, max_visits=10, max_cash=600_000)
    assert plan.visits == [2, 1]  # e-float visit needs no cash; the 9-lakh delivery does not fit
    assert plan.excluded[0][0] == 0 and "cash bag" in plan.excluded[0][1]
    assert plan.efloat_to_send == 200_000 and plan.cash_to_carry == 50_000


def test_tight_float_gets_best_split_not_escalation(params):
    # P90-level needs (1.77 lakh) fit in a 2-lakh float but the 99% targets (2.27 lakh) do not
    # -> best pro-rata split of the float, no escalation
    co, ci = [100_000, 130_000, 160_000], [80_000, 100_000, 120_000]
    r = _rec(params, 20_000, 180_000, 200_000, co, ci)
    assert r["action"][0] == TOP_UP_CASH
    assert r["extra_float_needed"][0] == 0
    assert r["target_cash"][0] + r["target_efloat"][0] > 200_000
    split = round(200_000 * r["target_cash"][0] / (r["target_cash"][0] + r["target_efloat"][0]), -3)
    assert abs(r["new_cash"][0] - split) <= params.round_to


def test_optimal_plan_beats_greedy_on_a_knapsack_trap():
    from floatwise.engine.allocate import plan_dso_optimal

    # greedy takes the single big 9-lakh delivery (value 10) and has no room left;
    # the optimum takes the two 5-lakh deliveries (value 9 + 8 = 17)
    action = np.array([TOP_UP_CASH] * 3, dtype=object)
    cash = np.array([900_000.0, 500_000.0, 500_000.0])
    prio = np.array([10.0, 9.0, 8.0])
    greedy = plan_dso(action, cash, prio, max_visits=10, max_cash=1_000_000)
    best = plan_dso_optimal(action, cash, prio, max_visits=10, max_cash=1_000_000)
    assert greedy.visits == [0]
    assert best.visits == [1, 2] and best.cash_to_carry == 1_000_000


def test_optimal_plan_never_worse_and_feasible():
    from floatwise.engine.allocate import plan_dso_optimal

    rng = np.random.default_rng(1)
    for _ in range(60):
        n = int(rng.integers(1, 26))
        action = rng.choice([TOP_UP_CASH, TOP_UP_EFLOAT, NO_ACTION], n).astype(object)
        cash = np.where(action == TOP_UP_EFLOAT, -rng.uniform(1e4, 4e5, n), rng.uniform(1e4, 6e5, n))
        prio = rng.uniform(0, 3e5, n)
        k, m = int(rng.integers(0, 12)), int(rng.integers(0, 2_000_000))
        g = plan_dso(action, cash, prio, k, m)
        o = plan_dso_optimal(action, cash, prio, k, m)
        assert len(o.visits) <= k and o.cash_to_carry <= m + 1000 * len(o.visits)
        assert all(action[i] != NO_ACTION for i in o.visits)
        assert prio[o.visits].sum() >= prio[g.visits].sum() - 1e-6
        assert len(o.visits) + len(o.excluded) == int((action != NO_ACTION).sum())
