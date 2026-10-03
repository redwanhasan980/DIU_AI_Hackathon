"""Synthetic data checks (SRS §5.4) + calendar, ledger and determinism tests."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from floatwise.data.calendar_bd import build_calendar, upcoming_events
from floatwise.data.generate import generate
from floatwise.data.simulate_status_quo import serve_day, status_quo_next_cash

# ---- calendar ---------------------------------------------------------------


def test_calendar_eid_flags(cfg):
    cal = build_calendar(cfg).set_index("date")
    for d in cfg.calendar.eid_fitr:
        assert cal.loc[pd.Timestamp(d), "is_eid_fitr"]
        assert cal.loc[pd.Timestamp(d) - pd.Timedelta(days=5), "days_to_eid_fitr"] == 5
    for d in cfg.calendar.eid_adha:
        assert cal.loc[pd.Timestamp(d), "is_eid_adha"]
    assert cal["is_eid_fitr"].sum() == len(cfg.calendar.eid_fitr)


def test_calendar_ramadan_and_salary(cfg):
    cal = build_calendar(cfg)
    assert cal["is_ramadan"].sum() == cfg.calendar.ramadan_days * len(cfg.calendar.eid_fitr)
    lo, hi = cfg.calendar.salary_window
    assert (cal.loc[cal["is_salary_window"], "day_of_month"].between(lo, hi)).all()
    assert cal["date"].is_unique and len(cal) == (cfg.dates.end - cfg.dates.start).days + 1


def test_demo_date_is_before_eid(cfg):
    events = upcoming_events(cfg, cfg.dates.demo_date)
    names = {e[0]: e[2] for e in events}
    assert names["Eid-ul-Fitr"] == 5


# ---- ledger mechanics -------------------------------------------------------


def test_serve_day_conserves_float_and_caps_service():
    cash = np.array([100.0, 0.0, 50.0])
    efloat = np.array([100.0, 200.0, 0.0])
    res = serve_day(
        cash, efloat, np.array([150.0, 50.0, 10.0]), np.array([20.0, 10.0, 80.0]), [0.5, 0.5], [0.5, 0.5]
    )
    np.testing.assert_allclose(res.cash + res.efloat, cash + efloat)
    assert (res.served_co <= np.array([150.0, 50.0, 10.0]) + 1e-9).all()
    # agent 2 starts with no cash: only the slot-1 cash-in (5) can fund the slot-2 cash-out
    assert res.served_co[1] == 5.0
    assert (res.cash >= 0).all() and (res.efloat >= 0).all()


def test_status_quo_rule_triggers_only_when_low(cfg):
    pol = cfg.policy.status_quo
    hist = np.full((2, 7), 100_000.0)
    cap = np.array([1_000_000.0, 1_000_000.0])
    new = status_quo_next_cash(
        pol, hist, hist, np.array([10_000.0, 500_000.0]), np.array([990_000.0, 500_000.0]), cap
    )
    assert new[0] == round(pol.target_ratio * 100_000, -3)  # topped up
    assert new[1] == 500_000.0  # untouched


# ---- generated sample quality (SRS §5.4) --------------------------------------


def test_no_negative_balances(sample):
    d = sample["daily"]
    for col in ("open_cash", "open_efloat", "close_cash", "close_efloat"):
        assert (d[col] >= 0).all(), col


def test_served_never_exceeds_demand(sample):
    d = sample["daily"]
    assert (d["cashout_amt"] <= d["cashout_demand_amt"]).all()
    assert (d["cashin_amt"] <= d["cashin_demand_amt"]).all()
    assert (d["unserved_cashout_amt"] >= 0).all()


def test_float_conservation(sample):
    d = sample["daily"].merge(sample["agents"][["agent_id", "float_capacity"]], on="agent_id")
    assert (abs(d["close_cash"] + d["close_efloat"] - d["float_capacity"]) <= 2).all()


def test_complete_panel(sample):
    d, cal = sample["daily"], sample["calendar"]
    assert len(d) == len(sample["agents"]) * len(cal)
    assert not d.duplicated(["agent_id", "date"]).any()


def test_every_archetype_present(sample):
    shares = sample["agents"]["archetype"].value_counts(normalize=True)
    assert len(shares) == 5 and shares.min() >= 0.1


def test_rural_eid_spike_visible(sample, cfg):
    d = sample["daily"].merge(sample["agents"][["agent_id", "archetype"]], on="agent_id")
    rural = d[d["archetype"] == "rural_remittance"].groupby("date")["cashout_demand_amt"].mean()
    for eid in cfg.calendar.eid_fitr:
        e = pd.Timestamp(eid)
        pre = rural[e - pd.Timedelta(days=7) : e - pd.Timedelta(days=1)].mean()
        base = rural[e - pd.Timedelta(days=37) : e - pd.Timedelta(days=30)].mean()
        assert pre >= 1.5 * base, (eid, pre, base)


def test_stockouts_concentrate_on_events(sample):
    d = sample["daily"].merge(sample["calendar"][["date", "event_name"]], on="date")
    pre_eid = d["event_name"].str.startswith("Pre Eid")
    normal = d["event_name"] == ""
    assert d.loc[pre_eid, "stockout_cash"].mean() > 3 * d.loc[normal, "stockout_cash"].mean()


def test_generation_is_deterministic(cfg):
    small = cfg.with_overrides(network={"n_agents": 12}, dates={"end": dt.date(2024, 3, 1)})
    a, b = generate(small)["daily"], generate(small)["daily"]
    pd.testing.assert_frame_equal(a, b)
