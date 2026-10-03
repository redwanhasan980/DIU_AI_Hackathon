"""Evaluate models vs baselines and precompute forecasts: `python -m floatwise.models.evaluate`.

Outputs (FR-FCST-5):
  artifacts/metrics.json        WAPE / MAE / pinball / coverage per split, slice, archetype, horizon
  artifacts/forecasts.parquet   quantile forecasts for every agent and origin in val + test (API reads it)
  artifacts/model_card.md
Evaluation is against the synthetic ground-truth demand (what customers wanted), not served volume.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from floatwise.config import Config, get_config
from floatwise.data.generate import load_dataset
from floatwise.features.build import Matrices, build_panel, origin_indices, to_matrices
from floatwise.models.baselines import BASELINES
from floatwise.models.predict import QuantileModels
from floatwise.models.train import split_panel

# ---- metrics ----------------------------------------------------------------


def wape(y: np.ndarray, yhat: np.ndarray) -> float:
    return float(np.abs(y - yhat).sum() / max(np.abs(y).sum(), 1e-9))


def mae(y: np.ndarray, yhat: np.ndarray) -> float:
    return float(np.abs(y - yhat).mean())


def pinball(y: np.ndarray, yq: np.ndarray, q: float) -> float:
    diff = y - yq
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    return float(np.mean((y >= lo) & (y <= hi)))


def improvement(base: float, model: float) -> float:
    return round(100.0 * (base - model) / base, 1) if base > 0 else 0.0


# ---- slicing ----------------------------------------------------------------


def slice_masks(
    cfg: Config, panel: pd.DataFrame, m: Matrices, calendar: pd.DataFrame, agents: pd.DataFrame
) -> dict[str, np.ndarray]:
    cal = calendar.set_index("date").reindex(m.dates)
    tidx = panel["target_idx"].to_numpy()
    before, after = -cfg.model.event_window[0], cfg.model.event_window[1]
    to_eid = np.minimum(cal["days_to_eid_fitr"].to_numpy(), cal["days_to_eid_adha"].to_numpy())[tidx]
    event = (to_eid <= before) | (cal["days_after_eid"].to_numpy()[tidx] <= after)
    salary = cal["is_salary_window"].to_numpy(dtype=bool)[tidx]
    arch = agents.set_index("agent_id").reindex(m.agent_ids)["archetype"].to_numpy()[panel["agent_idx"]]
    rural = np.array([cfg.archetypes[a].rural for a in arch])
    masks = {
        "overall": np.ones(len(panel), dtype=bool),
        "event_days": event,
        "salary_window": salary & ~event,
        "normal_days": ~event & ~salary,
        "rural": rural,
        "urban": ~rural,
    }
    for a in cfg.archetypes:
        masks[f"archetype:{a}"] = arch == a
    for h in range(1, cfg.model.horizons + 1):
        masks[f"horizon:{h}"] = panel["h"].to_numpy() == h
    return masks


def evaluate_split(cfg: Config, models: QuantileModels, panel: pd.DataFrame, masks: dict) -> dict:
    out: dict = {}
    qs = models.quantiles
    i50, i10, i90 = qs.index(0.5), qs.index(min(qs)), qs.index(max(qs))
    for target in models.targets:
        y = panel[f"demand_{target}"].to_numpy()
        pred = models.predict_amount(panel, target)
        base = {name: fn(panel, target) for name, fn in BASELINES.items()}
        res = {}
        for name, mask in masks.items():
            if mask.sum() == 0:
                continue
            ym, pm = y[mask], pred[mask]
            row = {
                "n": int(mask.sum()),
                "wape_model": round(wape(ym, pm[:, i50]), 4),
                "mae_model": round(mae(ym, pm[:, i50])),
                "coverage_p10_p90": round(coverage(ym, pm[:, i10], pm[:, i90]), 3),
                "pinball": {str(q): round(pinball(ym, pm[:, k], q)) for k, q in enumerate(qs)},
            }
            for bname, b in base.items():
                row[f"wape_{bname}"] = round(wape(ym, b[mask]), 4)
                row[f"improvement_vs_{bname}_pct"] = improvement(row[f"wape_{bname}"], row["wape_model"])
            res[name] = row
        out[target] = res
    return out


def acceptance(test: dict, cfg: Config) -> dict:
    co = test["cashout"]
    arch_ok = {
        k.split(":")[1]: v["wape_model"] <= v["wape_seasonal_naive"]
        for k, v in co.items()
        if k.startswith("archetype:")
    }
    checks = {
        "overall_improvement_vs_seasonal_naive_ge_20pct": co["overall"]["improvement_vs_seasonal_naive_pct"]
        >= 20,
        "event_improvement_vs_seasonal_naive_ge_35pct": co["event_days"]["improvement_vs_seasonal_naive_pct"]
        >= 35,
        "coverage_p10_p90_between_72_and_88pct": 0.72 <= co["overall"]["coverage_p10_p90"] <= 0.88,
        "no_archetype_worse_than_baseline": all(arch_ok.values()),
    }
    return {"checks": checks, "archetype_beats_baseline": arch_ok, "all_passed": all(checks.values())}


# ---- forecasts for the API / simulator -------------------------------------


def precompute_forecasts(cfg: Config, models: QuantileModels, m: Matrices, data: dict) -> pd.DataFrame:
    one = pd.Timedelta(days=1)
    origins = origin_indices(
        m, cfg, pd.Timestamp(cfg.dates.val_start) - one, pd.Timestamp(cfg.dates.test_end)
    )
    frames = []
    for chunk in np.array_split(origins, 8):
        panel = build_panel(cfg, m, data["calendar"], data["agents"], chunk)
        f = pd.DataFrame({
            "agent_id": m.agent_ids[panel["agent_idx"]],
            "origin": m.dates[panel["origin_idx"]],
            "date": m.dates[panel["origin_idx"]] + pd.to_timedelta(panel["h"], unit="D"),
            "horizon": panel["h"].astype(np.int8),
        })  # fmt: skip
        for target in models.targets:
            pred = models.predict_amount(panel, target)
            for k, q in enumerate(models.quantiles):
                f[f"{target}_p{int(round(q * 100)):02d}"] = np.round(pred[:, k]).astype(np.int64)
            f[f"actual_{target}"] = panel[f"demand_{target}"].round().astype("Int64")
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


def experiments_summary(art: Path) -> str:
    lines = []
    cens = art / "censoring_experiment.json"
    if cens.exists():
        c = json.loads(cens.read_text(encoding="utf-8"))
        rows = ", ".join(f"{k}: {v['pre_eid_above_p90']:.0%} above P90" for k, v in c["results"].items())
        lines.append(f"- Censoring mode on {c['holdout']}: {rows} → selected **{c['selected']}**.")
    qe = art / "quantile_experiment.json"
    if qe.exists():
        q = json.loads(qe.read_text(encoding="utf-8"))
        r = q["results"]
        lines.append(
            f"- Quantile architecture on {q['holdout']}: event pinball independent "
            f"{r['independent']['cashout']['mean_pinball_event']:,} vs spread {r['spread']['cashout']['mean_pinball_event']:,}; "
            f"event P10–P90 coverage {r['independent']['cashout']['coverage_event']:.0%} vs "
            f"{r['spread']['cashout']['coverage_event']:.0%}. Rule: {q['criterion']} → selected **{q['selected']}**."
        )
    pt = art / "policy_tuning.json"
    if pt.exists():
        p = json.loads(pt.read_text(encoding="utf-8"))
        sel = p["selected"]
        lines.append(
            f"- Policy (service level {sel['service_level']}, risk threshold {sel['risk_threshold']}) chosen on "
            f"{p['period']} by: {p['rule']}."
        )
    lines.append(
        "- Raw quantile models can cross around Eid peaks; predictions are re-ordered (rearrangement) so "
        "P10 ≤ P50 ≤ P90. SHAP drivers explain the raw median model."
    )
    return "\n".join(lines)


def model_card(meta: dict, metrics: dict, art: Path | None = None) -> str:
    co = metrics["test"]["cashout"]
    ci = metrics["test"]["cashin"]

    def line(name: str, r: dict) -> str:
        return (
            f"| {name} | {r['wape_model']:.3f} | {r['wape_seasonal_naive']:.3f} | "
            f"{r['wape_trailing_mean7']:.3f} | {r['improvement_vs_seasonal_naive_pct']:+.1f} % | "
            f"{r['coverage_p10_p90']:.0%} |"
        )

    rows = [
        line(f"Cash-out — {k.replace('archetype:', '')}", co[k])
        for k in ("overall", "event_days", "salary_window", "normal_days", "rural", "urban")
    ]
    rows += [line(f"Cash-out — {k.split(':')[1]}", v) for k, v in co.items() if k.startswith("archetype:")]
    rows += [line("Cash-in — overall", ci["overall"]), line("Cash-in — event_days", ci["event_days"])]
    checks = "\n".join(f"- {'✅' if ok else '❌'} {k}" for k, ok in metrics["acceptance"]["checks"].items())
    experiments = experiments_summary(art) if art is not None else "- (not recorded)"
    return f"""# FloatWise Model Card — {meta["version"]}

Generated {metrics["generated_at"]} by `make evaluate`. All numbers come from code (R-ML-5).

## Model
- Global LightGBM quantile regression, one model per target (cash-out, cash-in) and quantile {meta["quantiles"]}.
- Direct multi-horizon (h = 1..7 as a feature); target = served amount / agent's trailing 28-day mean.
- {len(meta["features"])} features: target-day calendar (Eid distance, salary window, Ramadan, …), lags and rolling
  stats known at the origin, previous-Eid multipliers, archetype/district, recent stockouts.
- Censoring: `{meta["censoring"]}` — on a stockout day the observed volume understates true demand. The mode was
  chosen on a held-out Eid (2025) by `scripts/censoring_experiment.py`; `inflate` lifts censored labels to the
  P75 ratio of uncensored peers (same archetype, same day).
- Trained on {meta["trained_on"]["start"]} → {meta["trained_on"]["end"]}; early stopping on validation
  {meta["early_stopping_on"]["start"]} → {meta["early_stopping_on"]["end"]}. Test 2026-01-01 → 2026-06-30 untouched.

## Test results (vs synthetic ground-truth demand, all horizons)
| Slice | WAPE model | WAPE seasonal-naive | WAPE trailing-7 | Δ vs naive | P10–P90 coverage |
|---|---|---|---|---|---|
{chr(10).join(rows)}

## Acceptance (SRS §6.4)
{checks}

## Model selection (never on the test period)
{experiments}

## Intended use & limits
- Operational liquidity planning for agents; recommendations always need human approval.
- Trained on synthetic data only; must be re-validated on governed real data before any pilot.
- Not for credit, lending or penalty decisions about agents.
"""


def run(cfg: Config, data: dict, verbose: bool = True) -> dict:
    t0 = time.time()
    m = to_matrices(data["daily"])
    models = QuantileModels.load(cfg)
    metrics: dict = {
        "version": models.version,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    for split in ("val", "test"):
        panel = split_panel(cfg, m, data, split, sampled=False)
        masks = slice_masks(cfg, panel, m, data["calendar"], data["agents"])
        metrics[split] = evaluate_split(cfg, models, panel, masks)
        co = metrics[split]["cashout"]
        event = co.get("event_days", {}).get("improvement_vs_seasonal_naive_pct", float("nan"))
        if not verbose:
            continue
        print(
            f"{split}: cash-out WAPE {co['overall']['wape_model']:.3f} "
            f"(naive {co['overall']['wape_seasonal_naive']:.3f}, "
            f"Δ {co['overall']['improvement_vs_seasonal_naive_pct']:+.1f}%); "
            f"event days Δ {event:+.1f}%{' (no Eid in this split)' if np.isnan(event) else ''}; "
            f"coverage {co['overall']['coverage_p10_p90']:.0%}"
        )
    metrics["acceptance"] = acceptance(metrics["test"], cfg)
    if verbose:
        print("acceptance:", metrics["acceptance"]["checks"])

    art: Path = cfg.artifacts_dir
    art.mkdir(parents=True, exist_ok=True)
    (art / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    meta = json.loads((cfg.models_dir / "meta.json").read_text(encoding="utf-8"))
    (art / "model_card.md").write_text(model_card(meta, metrics, art), encoding="utf-8")

    fc = precompute_forecasts(cfg, models, m, data)
    fc.to_parquet(art / "forecasts.parquet", index=False, compression="zstd")
    if verbose:
        print(f"forecasts: {len(fc):,} rows; done in {time.time() - t0:.0f}s")
    return metrics


def main() -> None:
    cfg = get_config()
    run(cfg, load_dataset(cfg.data_dir))


if __name__ == "__main__":
    main()
