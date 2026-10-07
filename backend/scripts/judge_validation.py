"""Reproducible judge-feedback experiments, entirely before the 2026 test period.

Run from backend: python scripts/judge_validation.py
Writes artifacts/judge_validation.json; leaves the submitted model and metrics intact.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from floatwise.config import get_config
from floatwise.data.generate import load_dataset
from floatwise.engine.recommend import PolicyParams
from floatwise.features.build import build_panel, origin_indices, to_matrices
from floatwise.models.baselines import BASELINES
from floatwise.models.calibration import IntervalCalibrator, event_mask
from floatwise.models.evaluate import coverage, pinball, wape
from floatwise.models.predict import QuantileModels
from floatwise.models.train import train
from floatwise.simulation.backtest import load_inputs, policy_metrics, run_policy


def score(panel: pd.DataFrame, predictions: dict, cfg) -> dict:
    ev = event_mask(panel, cfg.model.event_window)
    out = {}
    for target, pred in predictions.items():
        y = panel[f"demand_{target}"].to_numpy()
        out[target] = {}
        masks = {"overall": np.ones(len(panel), bool), "event_days": ev, "normal_days": ~ev}
        masks |= {f"horizon:{h}": panel["h"].to_numpy() == h for h in range(1, cfg.model.horizons + 1)}
        masks |= {
            f"archetype:{a}": panel["archetype_code"].to_numpy() == i for i, a in enumerate(cfg.archetypes)
        }
        for name, mask in masks.items():
            if not mask.any():
                continue
            out[target][name] = {
                "n": int(mask.sum()),
                "wape": round(wape(y[mask], pred[mask, 1]), 4),
                "coverage": round(coverage(y[mask], pred[mask, 0], pred[mask, 2]), 4),
                "width_bdt": round(float(np.mean(pred[mask, 2] - pred[mask, 0]))),
                "pinball": round(
                    float(
                        np.mean([pinball(y[mask], pred[mask, k], q) for k, q in enumerate((0.1, 0.5, 0.9))])
                    )
                ),
            }
    return out


def frame(panel, predictions, m):
    fc = pd.DataFrame(
        {
            "agent_id": m.agent_ids[panel["agent_idx"]],
            "origin": m.dates[panel["origin_idx"]],
            "horizon": panel["h"],
        }
    )
    for target, pred in predictions.items():
        for k, q in enumerate((10, 50, 90)):
            fc[f"{target}_p{q}"] = pred[:, k]
    return fc


def baseline_interval_arms(cfg, data, m, calibration, assessment) -> dict:
    """Give simple forecasts empirical uncertainty from the same calibration observations.

    A fair uncertainty-aware baseline supplements the deliberately collapsed point arms.
    No fold model, assessment outcomes or synthetic ground truth are used to fit these intervals.
    """
    cal_events = event_mask(calibration, cfg.model.event_window)
    ass_events = event_mask(assessment, cfg.model.event_window)
    result = {}
    for name, fn in BASELINES.items():
        predictions = {}
        for target in cfg.model.targets:
            cal_point, point = fn(calibration, target), fn(assessment, target)
            residual = (calibration[f"served_{target}"].to_numpy() - cal_point) / calibration[
                f"scale_{target}"
            ].to_numpy()
            valid = (calibration[f"censored_{target}"].to_numpy() == 0) & np.isfinite(residual)
            pred = np.repeat(point[:, None], 3, axis=1)
            for event in (False, True):
                for h in range(1, cfg.model.horizons + 1):
                    fit = valid & (cal_events == event) & (calibration["h"].to_numpy() == h)
                    if fit.sum() < cfg.validation.min_calibration_rows:
                        fit = valid & (cal_events == event)
                    if fit.sum() < cfg.validation.min_calibration_rows:
                        continue
                    lower, upper = np.quantile(residual[fit], (0.1, 0.9))
                    mask = (ass_events == event) & (assessment["h"].to_numpy() == h)
                    scale = assessment.loc[mask, f"scale_{target}"].to_numpy()
                    pred[mask, 0] = np.maximum(0, point[mask] + min(lower, 0) * scale)
                    pred[mask, 2] = point[mask] + max(upper, 0) * scale
            predictions[target] = pred
        inp = load_inputs(
            cfg,
            data,
            frame(assessment, predictions, m),
            cfg.validation.assessment_start,
            cfg.validation.assessment_end - pd.Timedelta(days=1),
        )
        trace = run_policy(cfg, inp, "floatwise", PolicyParams.from_config(cfg))
        result[f"{name}_empirical_intervals"] = {
            "forecast": score(assessment, predictions, cfg),
            "operations": policy_metrics(cfg, inp, trace),
        }
    return result


def main() -> None:
    base = get_config()
    v = base.validation
    if not (
        v.fit_end
        < v.early_stop_start
        <= v.early_stop_end
        < v.calibration_start
        <= v.calibration_end
        < v.assessment_start
        <= v.assessment_end
        < base.dates.test_start
    ):
        raise ValueError("Experiment periods must be disjoint and precede the test period")
    cfg = base.with_overrides(
        dates={"train_end": v.fit_end, "val_start": v.early_stop_start, "val_end": v.early_stop_end}
    )
    data = load_dataset(cfg.data_dir)
    m = to_matrices(data["daily"])

    def panel_between(start, end):
        origins = origin_indices(
            m,
            cfg,
            pd.Timestamp(start) - pd.Timedelta(days=cfg.model.horizons),
            pd.Timestamp(end) - pd.Timedelta(days=1),
        )
        panel = build_panel(cfg, m, data["calendar"], data["agents"], origins)
        target_days = m.dates[panel["target_idx"]]
        return panel.loc[
            (target_days >= pd.Timestamp(start)) & (target_days <= pd.Timestamp(end))
        ].reset_index(drop=True)

    calibration = panel_between(v.calibration_start, v.calibration_end)
    assessment = panel_between(v.assessment_start, v.assessment_end)
    report = {
        "data_kind": "synthetic",
        "fit_end": str(v.fit_end),
        "early_stopping": [str(v.early_stop_start), str(v.early_stop_end)],
        "calibration_period": [str(v.calibration_start), str(v.calibration_end)],
        "assessment_period": [str(v.assessment_start), str(v.assessment_end)],
        "test_period_used": False,
        "feature_ablations": {},
    }
    with tempfile.TemporaryDirectory(prefix="floatwise-validation-") as tmp:
        train(cfg, data, Path(tmp), verbose=False)
        models = QuantileModels.load(cfg, Path(tmp))

        def predict(panel):
            return {t: models.predict_amount(panel, t) for t in cfg.model.targets}

        raw = predict(assessment)
        cal = IntervalCalibrator.fit(
            calibration,
            predict(calibration),
            cfg.model.event_window,
            v.interval_coverage,
            v.min_calibration_rows,
        )
        calibrated = {t: cal.apply(assessment, raw[t], t) for t in raw}
        report["calibration"] = {
            "method": "normalised conformal expansion by event and horizon; uncensored served labels only",
            "target_coverage": v.interval_coverage,
            "adjustments": cal.adjustments,
            "raw": score(assessment, raw, cfg),
            "calibrated": score(assessment, calibrated, cfg),
            "production_promoted": False,
            "limitation": "Temporal dependence, censored labels and event shifts can defeat coverage; field validation required.",
        }
        report["baselines"] = {
            name: {
                target: round(wape(assessment[f"demand_{target}"].to_numpy(), fn(assessment, target)), 4)
                for target in cfg.model.targets
            }
            for name, fn in BASELINES.items()
        }
        for group, excluded in v.feature_groups.items():
            train(cfg, data, Path(tmp) / group, verbose=False, excluded_features=excluded)
            ablated = QuantileModels.load(cfg, Path(tmp) / group)
            preds = {t: ablated.predict_amount(assessment, t) for t in cfg.model.targets}
            report["feature_ablations"][group] = {
                "removed_features": excluded,
                "metrics": score(assessment, preds, cfg),
            }
            print(f"feature ablation complete: {group}", flush=True)

        # Exogenous demand stress with frozen origin features and forecasts: no tuning or retraining.
        shifted = {}
        for scenario in ("cashout_surge", "cashin_surge", "heavy_tail", "shifted_event"):
            stress = assessment.copy()
            rng = np.random.default_rng(cfg.seed)
            for target in cfg.model.targets:
                y = stress[f"demand_{target}"].to_numpy().copy()
                if scenario == f"{target}_surge":
                    y *= v.demand_shifts[scenario]
                elif scenario == "heavy_tail":
                    sigma = v.demand_shifts["heavy_tail_sigma"]
                    y *= rng.lognormal(-sigma * sigma / 2, sigma, len(y))
                elif scenario == "shifted_event":
                    # Within each agent and horizon, move the demand sequence relative to known calendar.
                    stress["_y"] = y
                    y = (
                        stress.groupby(["agent_idx", "h"], sort=False)["_y"]
                        .transform(
                            lambda s: s.shift(int(v.demand_shifts["event_shift_days"]), fill_value=s.iloc[0])
                        )
                        .to_numpy()
                    )
                stress[f"demand_{target}"] = y
            shifted[scenario] = score(stress, calibrated, cfg)
        report["robustness"] = {
            "protocol": "Exogenous demand shifts with frozen histories/forecasts; sensitivity, not independent field data or a closed-loop backtest",
            "scenarios": shifted,
        }

        # Planning ablations share next-day forecasts, true demand, balances and compliance draws.
        h1 = assessment[assessment["h"] == 1]
        start = v.assessment_start
        end = v.assessment_end - pd.Timedelta(days=1)
        inp = load_inputs(cfg, data, frame(assessment, raw, m), start, end)
        calibrated_inp = load_inputs(cfg, data, frame(assessment, calibrated, m), start, end)
        params = PolicyParams.from_config(cfg)
        sq = run_policy(cfg, inp, "status_quo")
        operations = {"status_quo": policy_metrics(cfg, inp, sq)}
        for name, source, planner, p in (
            ("full_raw", inp, "optimal", params),
            ("full_calibrated", calibrated_inp, "optimal", params),
            ("greedy_allocation", inp, "greedy", params),
            ("no_dso_visits", inp, "optimal", params),
            ("no_same_day_inflow_credit", inp, "optimal", replace(params, overlap_alpha=0)),
        ):
            tr = run_policy(
                cfg,
                source,
                "floatwise",
                p,
                max_visits=0 if name == "no_dso_visits" else None,
                allocator=planner,
            )
            operations[name] = policy_metrics(cfg, source, tr)
        # Point forecasting: identical P10/P50/P90 removes uncertainty while keeping the same engine.
        point_inp = replace(
            inp,
            co_q=np.repeat(inp.co_q[:, :, 1:2], 3, axis=2),
            ci_q=np.repeat(inp.ci_q[:, :, 1:2], 3, axis=2),
        )
        operations["median_only"] = policy_metrics(
            cfg, point_inp, run_policy(cfg, point_inp, "floatwise", params)
        )
        for name, fn in BASELINES.items():
            preds = {t: np.repeat(fn(h1, t)[:, None], 3, axis=1) for t in cfg.model.targets}
            baseline_inp = load_inputs(cfg, data, frame(h1, preds, m), start, end)
            operations[f"engine_with_{name}"] = policy_metrics(
                cfg, baseline_inp, run_policy(cfg, baseline_inp, "floatwise", params)
            )
        report["pipeline_ablations"] = operations
        report["baseline_intervals"] = baseline_interval_arms(cfg, data, m, calibration, assessment)
        report["pipeline_ablations"].update(
            {name: arm["operations"] for name, arm in report["baseline_intervals"].items()}
        )
        sensitivity = []
        for adherence in v.compliance_values:
            tr = run_policy(cfg, inp, "floatwise", params, compliance=adherence)
            for churn in v.churn_values:
                adjusted_cfg = cfg.with_overrides(business={"churn_prob_after_fail": churn})
                metrics = policy_metrics(adjusted_cfg, inp, tr)
                sensitivity.append({"compliance": adherence, "churn_probability": churn, **metrics})
        report["business_sensitivity"] = sensitivity
        report["limitations"] = [
            "No measured upay agent, DSO, revenue or retention outcomes.",
            "Customers-at-risk is a failure-count proxy, not distinct customers or observed churn.",
            "Synthetic feature and pipeline ablations do not establish causal value in production.",
        ]
    out = base.artifacts_dir / "judge_validation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
