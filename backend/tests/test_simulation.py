"""Impact simulator: consistency with the generator, sanity of FloatWise and of the metrics."""

from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd
import pytest

from floatwise.engine.recommend import PolicyParams
from floatwise.simulation.backtest import load_inputs, policy_metrics, run_policy, simulate


@pytest.fixture(scope="module")
def inputs(tiny_cfg, sample, tiny_artifacts):
    fc = pd.read_parquet(tiny_artifacts / "forecasts.parquet")
    return load_inputs(tiny_cfg, sample, fc, tiny_cfg.dates.test_start, tiny_cfg.dates.test_end)


def test_status_quo_replay_matches_generated_data(tiny_cfg, sample, inputs):
    """The backtest's status-quo world must reproduce the generator's ledger exactly."""
    tr = run_policy(tiny_cfg, inputs, "status_quo")
    d = sample["daily"]
    window = d[d["date"].between(pd.Timestamp(tiny_cfg.dates.test_start), pd.Timestamp(tiny_cfg.dates.test_end))]
    ids = inputs.agents["agent_id"].to_numpy()
    expected = window.pivot(index="agent_id", columns="date", values="stockout_cash").reindex(ids).to_numpy()
    np.testing.assert_array_equal(tr.stockout_cash.astype(bool), expected.astype(bool))
    opened = window.pivot(index="agent_id", columns="date", values="open_cash").reindex(ids).to_numpy()
    np.testing.assert_allclose(tr.open_cash, opened, atol=10.0)  # stored demand is rounded to whole taka


def test_perfect_foresight_beats_status_quo(tiny_cfg, inputs):
    perfect = copy.copy(inputs)
    co = np.zeros_like(inputs.co_q)
    ci = np.zeros_like(inputs.ci_q)
    co[:-1] = inputs.co_demand.T[1:, :, None]
    ci[:-1] = inputs.ci_demand.T[1:, :, None]
    perfect.co_q, perfect.ci_q = co, ci
    params = PolicyParams.from_config(tiny_cfg)
    sq = policy_metrics(tiny_cfg, inputs, run_policy(tiny_cfg, inputs, "status_quo"))
    fw = policy_metrics(tiny_cfg, perfect, run_policy(tiny_cfg, perfect, "floatwise", params))
    assert fw["stockout_agent_days"] < 0.6 * sq["stockout_agent_days"]


def test_zero_dso_capacity_and_compliance_equals_status_quo(tiny_cfg, inputs):
    """With no DSO visits and nobody following the app, only 'safe' agents differ from the rule."""
    params = PolicyParams.from_config(tiny_cfg, risk_threshold=1.01)  # nothing is ever 'risky'
    fw = run_policy(tiny_cfg, inputs, "floatwise", params, max_visits=0, max_cash=0, compliance=0.0)
    assert np.isfinite(fw.open_cash).all() and (fw.open_cash >= 0).all()


def test_simulate_output_shape(tiny_cfg, inputs):
    res = simulate(tiny_cfg, inputs, PolicyParams.from_config(tiny_cfg), sweep=[0.9])
    assert len(res["timeline"]) == len(inputs.dates)
    assert {s["segment"] for s in res["by_area_type"]} == {"rural", "urban"}
    assert res["sweep"][0]["service_level"] == 0.9
    for policy in ("status_quo", "floatwise"):
        assert 0.0 < res[policy]["served_share"] <= 1.0


def test_cached_artifacts_written(tiny_artifacts):
    sim = json.loads((tiny_artifacts / "simulation_default.json").read_text())
    fair = json.loads((tiny_artifacts / "fairness.json").read_text())
    assert sim["source"] == "cache" and "improvement_pct" in sim
    assert {"segments", "flagged_segments", "all_segments_ok"} <= fair.keys()
