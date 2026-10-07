"""Generate the empirical-interval baseline arms for an existing judge validation report.

Allows adding these independently calculated arms without retraining the fold models.
The main judge_validation script also generates them during a clean run.
"""

from __future__ import annotations

import json

import pandas as pd
from judge_validation import baseline_interval_arms

from floatwise.config import get_config
from floatwise.data.generate import load_dataset
from floatwise.features.build import build_panel, origin_indices, to_matrices


def main() -> None:
    cfg = get_config()
    data = load_dataset(cfg.data_dir)
    m = to_matrices(data["daily"])
    panels = []
    for start, end in (
        (cfg.validation.calibration_start, cfg.validation.calibration_end),
        (cfg.validation.assessment_start, cfg.validation.assessment_end),
    ):
        origins = origin_indices(
            m,
            cfg,
            pd.Timestamp(start) - pd.Timedelta(days=cfg.model.horizons),
            pd.Timestamp(end) - pd.Timedelta(days=1),
        )
        panel = build_panel(cfg, m, data["calendar"], data["agents"], origins)
        dates = m.dates[panel["target_idx"]]
        panels.append(
            panel.loc[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))].reset_index(drop=True)
        )
    path = cfg.artifacts_dir / "judge_validation.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if report["calibration_period"] != [
        str(cfg.validation.calibration_start),
        str(cfg.validation.calibration_end),
    ] or report["assessment_period"] != [
        str(cfg.validation.assessment_start),
        str(cfg.validation.assessment_end),
    ]:
        raise ValueError("Report/config period mismatch; run judge_validation.py instead")
    report["baseline_intervals"] = baseline_interval_arms(cfg, data, m, *panels)
    report["pipeline_ablations"].update(
        {name: arm["operations"] for name, arm in report["baseline_intervals"].items()}
    )
    # Normalize the old display name; metrics remain exactly as computed by its original arm.
    if "no_intraday_recovery" in report["pipeline_ablations"]:
        report["pipeline_ablations"]["no_same_day_inflow_credit"] = report["pipeline_ablations"].pop(
            "no_intraday_recovery"
        )
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"generated empirical-interval baseline comparisons: {path}")


if __name__ == "__main__":
    main()
