"""Quantile models: train on the sample, predict non-crossing quantiles, metrics behave."""

from __future__ import annotations

import numpy as np

from floatwise.features.build import to_matrices
from floatwise.models.baselines import seasonal_naive, trailing_mean7
from floatwise.models.evaluate import coverage, pinball, wape
from floatwise.models.predict import QuantileModels
from floatwise.models.train import split_by_date, split_panel


def test_split_is_time_ordered_and_disjoint(cfg, sample):
    m = to_matrices(sample["daily"])
    splits = split_by_date(cfg, m)
    tr, va, te = (splits[k][0] for k in ("train", "val", "test"))
    assert tr.max() < va.min() and va.max() < te.min()


def test_train_targets_stay_inside_split(cfg, sample):
    m = to_matrices(sample["daily"])
    p = split_panel(cfg, m, sample, "train", sampled=True)
    assert m.dates[p["target_idx"].max()] <= np.datetime64(cfg.dates.train_end)


def test_tiny_models_predict_non_crossing(cfg, sample, tiny_artifacts):
    models = QuantileModels.load(cfg, tiny_artifacts / "models")
    m = to_matrices(sample["daily"])
    panel = split_panel(cfg, m, sample, "test", sampled=False)
    for target in ("cashout", "cashin"):
        pred = models.predict_amount(panel, target)
        assert pred.shape == (len(panel), 3)
        assert (np.diff(pred, axis=1) >= 0).all()
        assert (pred >= 0).all()


def test_baselines_use_only_history(cfg, sample):
    m = to_matrices(sample["daily"])
    panel = split_panel(cfg, m, sample, "val", sampled=False).head(100)
    assert np.isfinite(seasonal_naive(panel, "cashout")).all()
    assert np.isfinite(trailing_mean7(panel, "cashin")).all()


def test_metric_functions():
    y = np.array([100.0, 200.0])
    assert wape(y, y) == 0.0
    assert wape(y, np.array([110.0, 190.0])) == 20 / 300
    assert pinball(y, y, 0.9) == 0.0
    assert pinball(np.array([100.0]), np.array([90.0]), 0.9) == 9.0  # under-forecast costs q
    assert coverage(y, y - 1, y + 1) == 1.0


def test_spread_mode_trains_and_never_crosses(tiny_cfg, sample, tmp_path):
    from floatwise.models.train import train

    cfg = tiny_cfg.with_overrides(model={"quantile_mode": "spread"})
    train(cfg, sample, tmp_path, verbose=False)
    models = QuantileModels.load(cfg, tmp_path)
    assert models.mode == "spread"
    m = to_matrices(sample["daily"])
    pred = models.predict_amount(split_panel(cfg, m, sample, "test", sampled=False), "cashout")
    assert (np.diff(pred, axis=1) >= 0).all()
