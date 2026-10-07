"""Versioned local model registry with explicit reviewed activation and rollback."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from floatwise.api.persistence import Conflict, OperationsDB, encode
from floatwise.config import Config, get_config
from floatwise.models.predict import QuantileModels


def register_model(cfg: Config, operations: OperationsDB, directory: Path, evaluation: dict) -> dict:
    model = QuantileModels.load(cfg, directory)
    files = sorted(directory.glob("*.txt")) + [directory / "meta.json"]
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.name.encode())
        digest.update(file.read_bytes())
    meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    record = {
        "version": model.version,
        "registered_at": dt.datetime.now(dt.UTC).isoformat(),
        "training_cutoff": meta["trained_on"]["end"],
        "feature_schema": hashlib.sha256(encode(model.features).encode()).hexdigest(),
        "binary_sha256": digest.hexdigest(),
        "evaluation": evaluation,
    }
    with operations.transaction() as db:
        previous = db.execute(
            "SELECT payload FROM integration_models WHERE version=?", (model.version,)
        ).fetchone()
        if previous:
            old = json.loads(previous[0])
            if old["binary_sha256"] != record["binary_sha256"]:
                raise Conflict("This model version was registered with different contents")
            return old
        db.execute(
            "INSERT INTO integration_models VALUES (?,?,?)",
            (model.version, str(directory.resolve()), encode(record)),
        )
        operations._audit(db, "model-cli", "model_registered", model.version, record)
    return record


def retrain(store) -> dict:
    """Fit/early-stop/assess on separate 2025 windows; never tune on 2026 test data."""
    from floatwise.models.baselines import BASELINES
    from floatwise.models.evaluate import coverage, slice_masks, wape
    from floatwise.models.train import split_panel, train

    cfg = store.cfg
    v = cfg.validation
    candidate_cfg = cfg.with_overrides(
        dates={"train_end": v.fit_end, "val_start": v.early_stop_start, "val_end": v.early_stop_end}
    )
    directory = cfg.artifacts_dir / "model_candidates" / dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%f")
    meta = train(candidate_cfg, store.data, directory)
    candidate = QuantileModels.load(candidate_cfg, directory)
    evaluation_cfg = candidate_cfg.with_overrides(
        dates={"val_start": v.assessment_start, "val_end": v.assessment_end}
    )
    panel = split_panel(evaluation_cfg, store.m, store.data, "val", sampled=False)
    results = {}
    passed = True
    store.integration.sync_model()
    with store.operations.connect() as db:
        incumbent_dir = Path(
            db.execute(
                "SELECT directory FROM integration_models WHERE version=?", (store.models.version,)
            ).fetchone()[0]
        )
    incumbent_meta = json.loads((incumbent_dir / "meta.json").read_text(encoding="utf-8"))
    incumbent_cutoff = max(incumbent_meta["trained_on"]["end"], incumbent_meta["early_stopping_on"]["end"])
    incumbent_eligible = incumbent_cutoff < str(v.assessment_start)
    masks = slice_masks(evaluation_cfg, panel, store.m, store.calendar, store.agents)
    lower = v.interval_coverage - cfg.integration.coverage_tolerance
    upper = v.interval_coverage + cfg.integration.coverage_tolerance
    for side in candidate.targets:
        y = panel[f"demand_{side}"].to_numpy()
        pred = candidate.predict_amount(panel, side)
        incumbent = store.models.predict_amount(panel, side) if incumbent_eligible else None
        baseline = {name: wape(y, fn(panel, side)) for name, fn in BASELINES.items()}
        score, interval = wape(y, pred[:, 1]), coverage(y, pred[:, 0], pred[:, 2])
        current = wape(y, incumbent[:, 1]) if incumbent is not None else None
        segment_coverage = {
            name: {"n": int(mask.sum()), "coverage": coverage(y[mask], pred[mask, 0], pred[mask, 2])}
            for name, mask in masks.items()
            if name in {"event_days", "rural", "urban"} and mask.any()
        }
        reliable_segments = all(
            row["n"] >= v.min_calibration_rows and lower <= row["coverage"] <= upper
            for row in segment_coverage.values()
        )
        side_pass = bool(
            current is not None
            and score <= min(current, *baseline.values())
            and lower <= interval <= upper
            and reliable_segments
            and "event_days" in segment_coverage
        )
        results[side] = {
            "wape": score,
            "incumbent_wape": current,
            "baseline_wape": baseline,
            "interval_coverage": interval,
            "segment_coverage": segment_coverage,
            "passed": side_pass,
        }
        passed &= side_pass
    report = {
        "candidate_version": meta["version"],
        "compared_with": store.models.version,
        "assessment_start": str(v.assessment_start),
        "assessment_end": str(v.assessment_end),
        "passed": passed,
        "results": results,
        "data": "synthetic",
        "reviewed": False,
        "incumbent_comparison_eligible": incumbent_eligible,
        "promotion_blocker": None
        if incumbent_eligible
        else "The current model used dates in this assessment window. A fresh future holdout is required before comparing or promoting; the 2026 final test is not reused for tuning.",
    }
    (directory / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return register_model(cfg, store.operations, directory, report)


def activate(store, version: str, reviewed: bool, rollback: bool = False) -> None:
    from floatwise.integration.service import Integration

    if not reviewed:
        raise Conflict("Activation requires --reviewed after inspecting the evaluation")
    with store.operations.transaction() as db:
        active = Integration.control(db, "active_model")
        if rollback:
            version = Integration.control(db, "previous_model")
            if not version:
                raise Conflict("No previous activation is available for rollback")
        row = db.execute(
            "SELECT directory,payload FROM integration_models WHERE version=?", (version,)
        ).fetchone()
        if not row:
            raise Conflict("Unknown registered model")
        record = json.loads(row[1])
        loaded = QuantileModels.load(store.cfg, Path(row[0]))
        features_hash = hashlib.sha256(encode(loaded.features).encode()).hexdigest()
        if (
            features_hash != record["feature_schema"]
            or loaded.features != store.models.features
            or loaded.quantiles != store.cfg.model.quantiles
            or loaded.targets != store.cfg.model.targets
        ):
            raise Conflict("Model feature schema is incompatible")
        digest = hashlib.sha256()
        directory = Path(row[0])
        for file in sorted(directory.glob("*.txt")) + [directory / "meta.json"]:
            digest.update(file.name.encode())
            digest.update(file.read_bytes())
        if digest.hexdigest() != record["binary_sha256"]:
            raise Conflict("Registered model contents changed")
        evaluation = record["evaluation"]
        if not rollback and (
            evaluation.get("passed") is not True
            or evaluation.get("compared_with") != active
            or evaluation.get("candidate_version") != version
        ):
            raise Conflict("Candidate must pass evaluation against the current active model")
        if not rollback:
            active_dir = Path(
                db.execute("SELECT directory FROM integration_models WHERE version=?", (active,)).fetchone()[
                    0
                ]
            )
            for path in (directory, active_dir):
                meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
                cutoff = max(meta["trained_on"]["end"], meta["early_stopping_on"]["end"])
                if evaluation.get("assessment_start", "") <= cutoff:
                    raise Conflict(
                        "Promotion assessment must follow both models' fit and early-stopping windows"
                    )
        Integration.set_control(db, "previous_model", active)
        Integration.set_control(db, "active_model", version)
        store.operations._audit(
            db,
            "model-cli",
            "model_rollback" if rollback else "model_activated",
            version,
            {"previous": active, "reviewed": True},
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["list", "retrain", "register", "activate", "rollback"])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--evaluation", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--reviewed", action="store_true")
    args = parser.parse_args()
    from floatwise.api.main import load_env_file
    from floatwise.api.store import Store

    load_env_file()
    store = Store(get_config())
    if args.action == "retrain":
        print(json.dumps(retrain(store), indent=2))
    elif args.action == "register":
        if not args.directory or not args.evaluation:
            parser.error("register requires --directory and --evaluation")
        print(
            json.dumps(
                register_model(
                    store.cfg,
                    store.operations,
                    args.directory,
                    json.loads(args.evaluation.read_text(encoding="utf-8")),
                ),
                indent=2,
            )
        )
    elif args.action in {"activate", "rollback"}:
        if args.action == "activate" and not args.version:
            parser.error("activate requires --version")
        activate(store, args.version or "", args.reviewed, rollback=args.action == "rollback")
        print("Model control updated; API and worker load the selected version on their next request.")
    else:
        print(json.dumps(store.integration.status()["models"], indent=2))


if __name__ == "__main__":
    main()
