"""R-ML-2 / R-ML-6: features at origin t must not change when anything after t changes."""

from __future__ import annotations

import numpy as np
import pandas as pd

from floatwise.features.build import build_panel, feature_columns, to_matrices


def _panel_at(cfg, sample, daily, t0_idx):
    m = to_matrices(daily)
    return build_panel(cfg, m, sample["calendar"], sample["agents"], np.array([t0_idx]))


def test_future_data_does_not_change_features(cfg, sample):
    daily = sample["daily"]
    dates = np.sort(daily["date"].unique())
    t0_idx = 400
    t0 = pd.Timestamp(dates[t0_idx])
    before = _panel_at(cfg, sample, daily, t0_idx)

    corrupted = daily.copy()
    future = corrupted["date"] > t0
    rng = np.random.default_rng(0)
    for col in ("cashout_amt", "cashin_amt", "cashout_demand_amt", "cashin_demand_amt"):
        corrupted.loc[future, col] = rng.integers(0, 10_000_000, future.sum())
    for col in ("stockout_cash", "stockout_efloat"):
        corrupted.loc[future, col] = ~corrupted.loc[future, col]
    after = _panel_at(cfg, sample, corrupted, t0_idx)

    feats = feature_columns(before)
    pd.testing.assert_frame_equal(before[feats], after[feats])
    # labels for future target days *should* change, proving the corruption reached them
    assert not np.allclose(before["label_cashout"], after["label_cashout"])


def test_ground_truth_is_never_a_feature(cfg, sample):
    panel = _panel_at(cfg, sample, sample["daily"], 300)
    feats = feature_columns(panel)
    assert not any("demand" in f or f.startswith(("label_", "served_", "censored_")) for f in feats)
    assert "h" in feats and "days_to_eid_fitr" in feats


def test_target_date_calendar_features_describe_target_day(cfg, sample):
    m = to_matrices(sample["daily"])
    eid_idx = int(np.where(m.dates == pd.Timestamp(cfg.calendar.eid_fitr[1]))[0][0])
    panel = build_panel(cfg, m, sample["calendar"], sample["agents"], np.array([eid_idx - 5]))
    row = panel[(panel["agent_idx"] == 0) & (panel["h"] == 5)].iloc[0]
    assert row["days_to_eid_fitr"] == 0  # the target day is Eid itself
