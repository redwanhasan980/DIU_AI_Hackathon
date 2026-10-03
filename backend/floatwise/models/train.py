"""Train global LightGBM quantile models: `python -m floatwise.models.train` (FR-FCST-2, FR-FCST-6)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from floatwise.config import Config, get_config
from floatwise.data.generate import load_dataset
from floatwise.features.build import (
    CATEGORICAL_FEATURES,
    Matrices,
    build_panel,
    feature_columns,
    origin_indices,
    to_matrices,
)
from floatwise.models.predict import model_path


def split_by_date(cfg: Config, m: Matrices) -> dict[str, tuple[np.ndarray, pd.Timestamp, pd.Timestamp]]:
    """Origin indices and target-date bounds per split. Time-based only (R-ML-1)."""
    d = cfg.dates
    ts = pd.Timestamp
    one = pd.Timedelta(days=1)
    return {
        "train": (origin_indices(m, cfg, ts(d.start), ts(d.train_end) - one), ts(d.start), ts(d.train_end)),
        "val": (origin_indices(m, cfg, ts(d.val_start) - one, ts(d.val_end) - one), ts(d.val_start),
                ts(d.val_end)),
        "test": (origin_indices(m, cfg, ts(d.test_start) - one, ts(d.test_end) - one), ts(d.test_start),
                 ts(d.test_end)),
    }  # fmt: skip


def split_panel(
    cfg: Config, m: Matrices, data: dict, split: str, sampled: bool, seed: int = 0
) -> pd.DataFrame:
    origins, lo, hi = split_by_date(cfg, m)[split]
    rng = np.random.default_rng(seed)
    panel = build_panel(
        cfg, m, data["calendar"], data["agents"], origins,
        horizons_per_origin=cfg.model.train_horizons_per_origin if sampled else None, rng=rng,
    )  # fmt: skip
    target_dates = m.dates[np.minimum(panel["target_idx"].to_numpy(), len(m.dates) - 1)]
    keep = (panel["target_idx"].to_numpy() < len(m.dates)) & (target_dates >= lo) & (target_dates <= hi)
    return panel.loc[keep].reset_index(drop=True)


def _usable(panel: pd.DataFrame, target: str, censoring: str) -> pd.DataFrame:
    """Training rows for one target. Censored = the target day had a stockout (FR-FCST-6)."""
    rows = panel[panel[f"label_{target}"].notna()]
    cens = rows[f"censored_{target}"] == 1
    if censoring == "exclude":
        return rows[~cens]
    if censoring == "inflate":
        # unseen demand >= served: lift censored labels to the P75 ratio of uncensored peers
        # (same archetype, same target day)
        label = f"label_{target}"
        peers = rows[~cens].groupby(["archetype_code", "target_idx"])[label].quantile(0.75).rename("peer")
        rows = rows.join(peers, on=["archetype_code", "target_idx"])
        lifted = np.fmax(rows[label], rows["peer"])
        rows = rows.assign(**{label: np.where(cens, lifted, rows[label])}).drop(columns="peer")
    return rows


def train(cfg: Config, data: dict, models_dir: Path, verbose: bool = True) -> dict:
    t0 = time.time()
    m = to_matrices(data["daily"])
    train_p = split_panel(cfg, m, data, "train", sampled=True, seed=cfg.seed)
    val_p = split_panel(cfg, m, data, "val", sampled=True, seed=cfg.seed + 1)
    features = feature_columns(train_p)
    if verbose:
        print(
            f"panel: train {len(train_p):,} rows, val {len(val_p):,} rows, {len(features)} features "
            f"({time.time() - t0:.0f}s)"
        )

    models_dir.mkdir(parents=True, exist_ok=True)
    best_iters = {}
    for target in cfg.model.targets:
        tr = _usable(train_p, target, cfg.model.censoring)
        va = _usable(val_p, target, cfg.model.censoring)
        for q in cfg.model.quantiles:
            t1 = time.time()
            model = lgb.LGBMRegressor(objective="quantile", alpha=q, random_state=cfg.seed, **cfg.model.lgbm)
            model.fit(
                tr[features], tr[f"label_{target}"],
                eval_X=(va[features],),
                eval_y=(va[f"label_{target}"],),
                categorical_feature=CATEGORICAL_FEATURES,
                callbacks=[lgb.early_stopping(30, verbose=False)],
            )  # fmt: skip
            model.booster_.save_model(str(model_path(models_dir, target, q)))
            best_iters[f"{target}_q{q}"] = int(model.best_iteration_ or model.n_estimators)
            if verbose:
                print(
                    f"  {target} q={q}: {best_iters[f'{target}_q{q}']} trees, "
                    f"{len(tr):,} rows ({time.time() - t1:.0f}s)"
                )

    digest = hashlib.sha1()
    for target in cfg.model.targets:
        for q in cfg.model.quantiles:
            digest.update(model_path(models_dir, target, q).read_bytes())
    meta = {
        "version": f"fw-{digest.hexdigest()[:8]}",
        "features": features,
        "categorical": CATEGORICAL_FEATURES,
        "quantiles": cfg.model.quantiles,
        "targets": cfg.model.targets,
        "censoring": cfg.model.censoring,
        "best_iterations": best_iters,
        "train_rows": len(train_p),
        "trained_on": {"start": str(cfg.dates.start), "end": str(cfg.dates.train_end)},
        "early_stopping_on": {"start": str(cfg.dates.val_start), "end": str(cfg.dates.val_end)},
    }
    (models_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    if verbose:
        print(f"saved {meta['version']} to {models_dir} in {time.time() - t0:.0f}s")
    return meta


def main() -> None:
    cfg = get_config()
    train(cfg, load_dataset(cfg.data_dir), cfg.models_dir)


if __name__ == "__main__":
    main()
