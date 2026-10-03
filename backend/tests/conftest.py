from __future__ import annotations

import pytest

from floatwise.config import Config, get_config
from floatwise.data.generate import load_dataset


@pytest.fixture(scope="session")
def cfg() -> Config:
    return get_config()


@pytest.fixture(scope="session")
def sample(cfg: Config):
    """The committed 50-agent sample (data/sample/), regenerated with `make sample`."""
    return load_dataset(cfg.sample_dir)


@pytest.fixture(scope="session")
def tiny_cfg(cfg: Config, tmp_path_factory) -> Config:
    """Config whose artifacts dir is a temp folder and whose models are tiny (fast tests)."""
    art = tmp_path_factory.mktemp("artifacts")
    lgbm = {**cfg.model.lgbm, "n_estimators": 25, "num_leaves": 15, "min_child_samples": 20}
    return cfg.with_overrides(paths={"artifacts_dir": str(art)}, model={"lgbm": lgbm})


@pytest.fixture(scope="session")
def tiny_artifacts(tiny_cfg: Config, sample):
    """Run the whole pipeline on the sample with tiny models into a temp artifacts dir.

    Produces models, metrics.json, forecasts.parquet, simulation_default.json and fairness.json —
    everything the API needs — so tests never depend on `make all`.
    """
    from floatwise.models import evaluate
    from floatwise.models.train import train
    from floatwise.simulation import backtest

    train(tiny_cfg, sample, tiny_cfg.models_dir, verbose=False)
    evaluate.run(tiny_cfg, sample, verbose=False)
    backtest.run(tiny_cfg, sample, verbose=False)
    return tiny_cfg.artifacts_dir
