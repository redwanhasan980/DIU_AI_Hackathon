"""Impact simulator (FR-SIM-1..5): status quo vs FloatWise on the same true demand.

`python -m floatwise.simulation.backtest` writes artifacts/simulation_default.json and fairness.json.

Both policies start from the same balances and face identical (ground-truth) demand. Each evening:
  * status quo  — every agent applies today's rule of thumb (trailing 7-day mean);
  * FloatWise   — the engine recommends actions from next-day quantile forecasts; each DSO visits the
                  highest-priority agents within its visit and cash-bag limits. Agents that are not
                  visited get the advice in the app and self-rebalance at the distributor point, as agents
                  do today; only a share (`self_rebalance_compliance`) follows it, the rest keep their own
                  rule of thumb.
Forecasts come from status-quo-world history, which slightly understates demand in the FloatWise
world, so results are conservative (docs/DATA_ASSUMPTIONS.md §9).
"""

from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from floatwise.config import Config, get_config
from floatwise.data.generate import load_dataset
from floatwise.data.simulate_status_quo import serve_day, status_quo_next_cash
from floatwise.engine.allocate import PLANNERS
from floatwise.engine.recommend import PolicyParams, recommend


@dataclass
class SimInputs:
    agents: pd.DataFrame
    dates: pd.DatetimeIndex  # simulated days
    co_demand: np.ndarray  # (n_agents, n_days) ground truth
    ci_demand: np.ndarray
    start_cash: np.ndarray
    hist_co: np.ndarray  # (n_agents, lookback) served history before the first day
    hist_ci: np.ndarray
    co_q: np.ndarray  # (n_days, n_agents, 3) forecasts made at the close of each day for the next day
    ci_q: np.ndarray
    capacity: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.capacity = self.agents["float_capacity"].to_numpy(dtype=float)


def load_inputs(cfg: Config, data: dict, forecasts: pd.DataFrame, start: dt.date, end: dt.date) -> SimInputs:
    agents = data["agents"].sort_values("agent_id").reset_index(drop=True)
    ids = agents["agent_id"].to_numpy()
    daily = data["daily"].sort_values(["agent_id", "date"])
    dates = pd.date_range(start, end, freq="D")
    window = daily[daily["date"].between(dates[0], dates[-1])]

    def mat(frame: pd.DataFrame, col: str) -> np.ndarray:
        return frame.pivot(index="agent_id", columns="date", values=col).reindex(ids).to_numpy(dtype=float)

    look = cfg.policy.status_quo.lookback_days
    hist = daily[daily["date"].between(dates[0] - pd.Timedelta(days=look), dates[0] - pd.Timedelta(days=1))]
    first = window[window["date"] == dates[0]].set_index("agent_id").reindex(ids)

    fc = forecasts[(forecasts["horizon"] == 1) & forecasts["origin"].isin(dates)]
    co_q = np.zeros((len(dates), len(ids), 3))
    ci_q = np.zeros((len(dates), len(ids), 3))
    day_pos = {d: i for i, d in enumerate(dates)}
    agent_pos = {a: i for i, a in enumerate(ids)}
    di = fc["origin"].map(day_pos).to_numpy()
    ai = fc["agent_id"].map(agent_pos).to_numpy()
    for k, q in enumerate(("p10", "p50", "p90")):
        co_q[di, ai, k] = fc[f"cashout_{q}"].to_numpy()
        ci_q[di, ai, k] = fc[f"cashin_{q}"].to_numpy()

    return SimInputs(
        agents=agents,
        dates=dates,
        co_demand=mat(window, "cashout_demand_amt"),
        ci_demand=mat(window, "cashin_demand_amt"),
        start_cash=first["open_cash"].to_numpy(dtype=float),
        hist_co=mat(hist, "cashout_amt"),
        hist_ci=mat(hist, "cashin_amt"),
        co_q=co_q,
        ci_q=ci_q,
    )


@dataclass
class SimTrace:
    stockout_cash: np.ndarray
    stockout_efloat: np.ndarray
    unserved_co: np.ndarray
    unserved_ci: np.ndarray
    open_cash: np.ndarray
    trips: np.ndarray


def run_policy(
    cfg: Config,
    inp: SimInputs,
    policy: str,
    params: PolicyParams | None = None,
    max_visits: int | None = None,
    max_cash: int | None = None,
    compliance: float | None = None,
    allocator: str | None = None,
) -> SimTrace:
    n_a, n_d = inp.co_demand.shape
    cap = inp.capacity
    cash = inp.start_cash.copy()
    efloat = cap - cash
    look = cfg.policy.status_quo.lookback_days
    hist_co = np.concatenate([inp.hist_co, np.zeros((n_a, n_d))], axis=1)
    hist_ci = np.concatenate([inp.hist_ci, np.zeros((n_a, n_d))], axis=1)
    h0 = inp.hist_co.shape[1]
    tr = SimTrace(*(np.zeros((n_a, n_d)) for _ in range(6)))
    dso = inp.agents["dso_id"].to_numpy()
    dso_groups = [np.where(dso == d)[0] for d in np.unique(dso)]
    k_visits = cfg.policy.dso.max_visits if max_visits is None else max_visits
    m_cash = cfg.policy.dso.max_cash if max_cash is None else max_cash
    comply = cfg.policy.floatwise.self_rebalance_compliance if compliance is None else compliance
    plan_dso = PLANNERS[allocator or cfg.policy.dso.allocator]
    rng = np.random.default_rng(cfg.seed)  # same draws for every run -> comparable scenarios

    for d in range(n_d):
        tr.open_cash[:, d] = cash
        res = serve_day(
            cash,
            efloat,
            inp.co_demand[:, d],
            inp.ci_demand[:, d],
            cfg.demand.co_slot_profile,
            cfg.demand.ci_slot_profile,
        )
        tr.unserved_co[:, d] = inp.co_demand[:, d] - res.served_co
        tr.unserved_ci[:, d] = inp.ci_demand[:, d] - res.served_ci
        tr.stockout_cash[:, d] = tr.unserved_co[:, d] > 1.0
        tr.stockout_efloat[:, d] = tr.unserved_ci[:, d] > 1.0
        hist_co[:, h0 + d] = res.served_co
        hist_ci[:, h0 + d] = res.served_ci

        lo = h0 + d + 1 - look
        sq_cash = status_quo_next_cash(
            cfg.policy.status_quo,
            hist_co[:, lo : h0 + d + 1],
            hist_ci[:, lo : h0 + d + 1],
            res.cash,
            res.efloat,
            cap,
        )
        if policy == "status_quo":
            new_cash = sq_cash
        else:
            assert params is not None
            rec = recommend(params, res.cash, res.efloat, cap, inp.co_q[d], inp.ci_q[d])
            follows_app = rng.random(n_a) < comply
            # not visited: compliant agents self-rebalance to the advice, the others keep their own rule
            new_cash = np.where(follows_app, rec["new_cash"], sq_cash)
            for idx in dso_groups:
                plan = plan_dso(
                    rec["action"][idx],
                    rec["cash_delta"][idx],
                    rec["expected_shortfall"][idx],
                    k_visits,
                    m_cash,
                )
                chosen = idx[plan.visits]
                new_cash[chosen] = rec["new_cash"][chosen]
            # agents the engine judges safe keep their balances instead of following the rule of thumb
            safe = rec["action"] == "NO_ACTION"
            new_cash[safe] = res.cash[safe]
        tr.trips[:, d] = np.abs(new_cash - res.cash) >= 1000
        cash, efloat = new_cash, cap - new_cash
    return tr


def policy_metrics(cfg: Config, inp: SimInputs, tr: SimTrace, mask: np.ndarray | None = None) -> dict:
    sel = np.ones(len(inp.agents), dtype=bool) if mask is None else mask
    b = cfg.business
    ticket = inp.agents["archetype"].map({a: c.ticket for a, c in cfg.archetypes.items()}).to_numpy()[:, None]
    so = np.maximum(tr.stockout_cash, tr.stockout_efloat)[sel]
    fail_co = tr.unserved_co[sel].sum()
    fail_ci = tr.unserved_ci[sel].sum()
    fail_co_cnt = (tr.unserved_co / ticket)[sel].sum()
    # upay keeps the cash-out fee minus the agent + distributor commission
    fee = inp.agents["archetype"].map(b.cashout_fee_rate).to_numpy()
    upay_margin = np.maximum(fee - b.channel_rate, 0.0)
    lost_upay_fee = (tr.unserved_co.sum(axis=1) * upay_margin)[sel].sum()
    fail_ci_cnt = (tr.unserved_ci / ticket)[sel].sum()
    demand = inp.co_demand[sel].sum() + inp.ci_demand[sel].sum()
    return {
        "stockout_agent_days": int(so.sum()),
        "cash_stockout_days": int(tr.stockout_cash[sel].sum()),
        "efloat_stockout_days": int(tr.stockout_efloat[sel].sum()),
        "failed_cashout_count": int(round(fail_co_cnt)),
        "failed_cashout_bdt": int(round(fail_co)),
        "failed_cashin_count": int(round(fail_ci_cnt)),
        "failed_cashin_bdt": int(round(fail_ci)),
        "lost_commission_bdt": int(round((fail_co + fail_ci) * b.channel_rate)),
        "lost_upay_fee_bdt": int(round(lost_upay_fee)),
        "customers_at_risk": int(round(fail_co_cnt * b.churn_prob_after_fail)),
        "avg_cash_held_bdt": int(round(tr.open_cash[sel].mean())),
        "rebalancing_trips": int(tr.trips[sel].sum()),
        "served_share": round(1.0 - (fail_co + fail_ci) / max(demand, 1.0), 4),
    }


def _pct(before: float, after: float) -> float:
    return round(100.0 * (before - after) / before, 1) if before else 0.0


def _segment(cfg, inp, sq, fw, name, mask) -> dict:
    a, b = policy_metrics(cfg, inp, sq, mask), policy_metrics(cfg, inp, fw, mask)
    return {
        "segment": name,
        "n_agents": int(mask.sum()),
        "status_quo_stockouts": a["stockout_agent_days"],
        "floatwise_stockouts": b["stockout_agent_days"],
        "stockout_reduction_pct": _pct(a["stockout_agent_days"], b["stockout_agent_days"]),
        "status_quo_failed_bdt": a["failed_cashout_bdt"] + a["failed_cashin_bdt"],
        "floatwise_failed_bdt": b["failed_cashout_bdt"] + b["failed_cashin_bdt"],
    }


def simulate(
    cfg: Config,
    inp: SimInputs,
    params: PolicyParams,
    max_visits: int | None = None,
    max_cash: int | None = None,
    sweep: list[float] | None = None,
) -> dict:
    sq = run_policy(cfg, inp, "status_quo")
    fw = run_policy(cfg, inp, "floatwise", params, max_visits, max_cash)
    a, b = policy_metrics(cfg, inp, sq), policy_metrics(cfg, inp, fw)
    days = len(inp.dates)
    per = 1000.0 / len(inp.agents) * 30.0 / days
    idle_cost = (a["avg_cash_held_bdt"] - b["avg_cash_held_bdt"]) * cfg.business.idle_cash_annual_cost / 12
    arch = inp.agents["archetype"].to_numpy()
    rural = np.array([cfg.archetypes[x].rural for x in arch])
    result = {
        "start": inp.dates[0].date().isoformat(),
        "end": inp.dates[-1].date().isoformat(),
        "n_agents": len(inp.agents),
        "params": {
            "service_level": params.service_level,
            "risk_threshold": params.risk_threshold,
            "overlap_alpha": params.overlap_alpha,
            "max_visits": float(cfg.policy.dso.max_visits if max_visits is None else max_visits),
            "max_cash": float(cfg.policy.dso.max_cash if max_cash is None else max_cash),
        },
        "status_quo": a,
        "floatwise": b,
        "improvement_pct": {
            "stockout_agent_days": _pct(a["stockout_agent_days"], b["stockout_agent_days"]),
            "failed_cashout_bdt": _pct(a["failed_cashout_bdt"], b["failed_cashout_bdt"]),
            "failed_total_bdt": _pct(a["failed_cashout_bdt"] + a["failed_cashin_bdt"],
                                     b["failed_cashout_bdt"] + b["failed_cashin_bdt"]),
            "lost_commission_bdt": _pct(a["lost_commission_bdt"], b["lost_commission_bdt"]),
            "lost_upay_fee_bdt": _pct(a["lost_upay_fee_bdt"], b["lost_upay_fee_bdt"]),
            "avg_cash_held_bdt": _pct(a["avg_cash_held_bdt"], b["avg_cash_held_bdt"]),
            "rebalancing_trips": _pct(a["rebalancing_trips"], b["rebalancing_trips"]),
        },
        "per_1000_agents_month": {
            "stockout_days_avoided": int(round((a["stockout_agent_days"] - b["stockout_agent_days"]) * per)),
            "failed_transactions_avoided": int(round(
                (a["failed_cashout_count"] + a["failed_cashin_count"]
                 - b["failed_cashout_count"] - b["failed_cashin_count"]) * per)),
            "failed_value_avoided_bdt": int(round(
                (a["failed_cashout_bdt"] + a["failed_cashin_bdt"]
                 - b["failed_cashout_bdt"] - b["failed_cashin_bdt"]) * per)),
            "commission_recovered_bdt": int(round((a["lost_commission_bdt"] - b["lost_commission_bdt"]) * per)),
            "upay_fee_recovered_bdt": int(round((a["lost_upay_fee_bdt"] - b["lost_upay_fee_bdt"]) * per)),
            "customers_retained": int(round((a["customers_at_risk"] - b["customers_at_risk"]) * per)),
            "extra_trips": int(round((b["rebalancing_trips"] - a["rebalancing_trips"]) * per)),
            "idle_cash_cost_saved_bdt": int(round(idle_cost * 1000.0)),
        },
        "upay_network_month": {},  # filled below
        "timeline": [
            {
                "date": inp.dates[d].date().isoformat(),
                "status_quo_stockouts": int(np.maximum(sq.stockout_cash, sq.stockout_efloat)[:, d].sum()),
                "floatwise_stockouts": int(np.maximum(fw.stockout_cash, fw.stockout_efloat)[:, d].sum()),
                "status_quo_failed_bdt": int(round(sq.unserved_co[:, d].sum() + sq.unserved_ci[:, d].sum())),
                "floatwise_failed_bdt": int(round(fw.unserved_co[:, d].sum() + fw.unserved_ci[:, d].sum())),
            }
            for d in range(days)
        ],
        "by_archetype": [_segment(cfg, inp, sq, fw, x, arch == x) for x in cfg.archetypes],
        "by_area_type": [_segment(cfg, inp, sq, fw, "rural", rural), _segment(cfg, inp, sq, fw, "urban", ~rural)],
        "sweep": [],
    }  # fmt: skip
    # linear scale-up to upay's whole agent network (public agent count; an ASSUMPTION, labelled in the UI)
    scale = cfg.business.upay_agents / 1000.0
    result["upay_network_month"] = {"agents": cfg.business.upay_agents} | {
        k: int(round(result["per_1000_agents_month"][k] * scale))
        for k in ("stockout_days_avoided", "failed_value_avoided_bdt", "upay_fee_recovered_bdt",
                  "commission_recovered_bdt", "customers_retained")
    }  # fmt: skip
    for s in sweep or []:
        t = run_policy(
            cfg, inp, "floatwise", PolicyParams.from_config(cfg, service_level=s), max_visits, max_cash
        )
        m = policy_metrics(cfg, inp, t)
        result["sweep"].append({
            "service_level": s,
            "stockout_agent_days": m["stockout_agent_days"],
            "failed_bdt": m["failed_cashout_bdt"] + m["failed_cashin_bdt"],
            "avg_cash_held_bdt": m["avg_cash_held_bdt"],
            "rebalancing_trips": m["rebalancing_trips"],
        })  # fmt: skip
    return result


def fairness_report(cfg: Config, sim: dict, metrics: dict) -> dict:
    """R-AI-7: forecast error and stockout reduction per segment; flag any segment worse than baseline."""
    co = metrics["test"]["cashout"]
    rows = []
    for seg in sim["by_archetype"] + sim["by_area_type"]:
        key = seg["segment"] if seg["segment"] in ("rural", "urban") else f"archetype:{seg['segment']}"
        f = co[key]
        rows.append({
            **seg,
            "wape_model": f["wape_model"],
            "wape_seasonal_naive": f["wape_seasonal_naive"],
            "forecast_beats_baseline": f["wape_model"] <= f["wape_seasonal_naive"],
            "service_not_worse": seg["floatwise_stockouts"] <= seg["status_quo_stockouts"],
        })  # fmt: skip
    flagged = [r["segment"] for r in rows if not (r["forecast_beats_baseline"] and r["service_not_worse"])]
    return {"segments": rows, "flagged_segments": flagged, "all_segments_ok": not flagged}


def run(cfg: Config, data: dict, verbose: bool = True) -> dict:
    t0 = time.time()
    forecasts = pd.read_parquet(cfg.artifacts_dir / "forecasts.parquet")
    params = PolicyParams.from_config(cfg)
    inp = load_inputs(cfg, data, forecasts, cfg.dates.test_start, cfg.dates.test_end)
    sim = simulate(cfg, inp, params, sweep=cfg.policy.sweep_service_levels)
    sim["source"] = "cache"
    art = cfg.artifacts_dir
    (art / "simulation_default.json").write_text(json.dumps(sim, indent=2))
    metrics = json.loads((art / "metrics.json").read_text())
    (art / "fairness.json").write_text(json.dumps(fairness_report(cfg, sim, metrics), indent=2))
    if verbose:
        a, b = sim["status_quo"], sim["floatwise"]
        print(f"test {sim['start']} → {sim['end']}, {sim['n_agents']} agents ({time.time() - t0:.0f}s)")
        for k in (
            "stockout_agent_days",
            "failed_cashout_bdt",
            "failed_cashin_bdt",
            "avg_cash_held_bdt",
            "rebalancing_trips",
        ):
            print(f"  {k:22s} status quo {a[k]:>14,}  FloatWise {b[k]:>14,}")
        print("  improvement %:", sim["improvement_pct"])
        print(
            "  sweep:",
            [(x["service_level"], x["stockout_agent_days"], x["avg_cash_held_bdt"]) for x in sim["sweep"]],
        )
    return sim


def main() -> None:
    cfg = get_config()
    run(cfg, load_dataset(cfg.data_dir))


if __name__ == "__main__":
    main()
