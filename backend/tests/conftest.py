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
