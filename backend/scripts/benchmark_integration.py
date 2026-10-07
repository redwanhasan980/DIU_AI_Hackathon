"""Measured local event/projection/feature/inference/planning benchmark.

Uses an isolated temporary SQLite DB and replicated synthetic agent histories.
Does not change operational state, train models, measure HTTP load, or simulate
money movement. Run explicitly; no capacity claims are generated before execution.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import tempfile
import time
from pathlib import Path

import numpy as np

from floatwise.api.persistence import OperationsDB
from floatwise.api.store import Store
from floatwise.config import get_config
from floatwise.engine.allocate import PLANNERS
from floatwise.engine.recommend import recommend
from floatwise.features.build import Matrices, build_panel
from floatwise.integration.service import Integration
from floatwise.schemas import IntegrationEvent


class BenchmarkStore:
    """Shares loaded baseline arrays while mapping larger populations onto synthetic seeds."""

    def __init__(self, base: Store, count: int, directory: Path):
        self.cfg = base.cfg
        self.seed_store = base
        self.indices = np.arange(count) % len(base.agents)
        self.ids = np.array([f"AG{i:05d}" for i in range(count)])
        self.agents = base.agents.iloc[self.indices].copy().reset_index(drop=True)
        self.agents["agent_id"] = self.ids
        # Replicate groups, rather than placing every clone in the original DSO group.
        self.agents["dso_id"] = [f"DSO{i // self.cfg.network.agents_per_dso:05d}" for i in range(count)]
        self.agent_pos = {agent: i for i, agent in enumerate(self.ids)}
        self.capacity = base.capacity[self.indices]
        self.calendar, self.date_pos, self.models = base.calendar, base.date_pos, base.models
        self.metrics, self.training_reference = base.metrics, base.training_reference
        self.operations = OperationsDB(directory / "benchmark.sqlite3")
        self.integration = Integration(self)

    def agent_index(self, agent: str) -> int:
        return self.agent_pos[agent]

    def check_date(self, day: dt.date) -> None:
        self.seed_store.check_date(day)


def elapsed(start: float) -> float:
    return round(time.perf_counter() - start, 4)


def measure(base: Store, count: int, batch_size: int) -> dict:
    day = base.cfg.dates.demo_date
    t = base.date_pos[day]
    with tempfile.TemporaryDirectory(prefix="floatwise-benchmark-") as temporary:
        store = BenchmarkStore(base, count, Path(temporary))
        integration = store.integration
        start = time.perf_counter()
        for agent, seed in zip(store.ids, store.indices, strict=True):
            bodies = [
                {
                    "kind": "transaction",
                    "side": side,
                    "outcome": "served",
                    "amount": max(1, int(base.m.y[side][seed, t])),
                }
                for side in ("cashin", "cashout")
            ] + [
                {
                    "kind": "balance_snapshot",
                    "sequence": 1,
                    "cash": int(base.close_cash[seed, t]),
                    "efloat": int(base.close_efloat[seed, t]),
                },
                {"kind": "day_closed"},
            ]
            for sequence, payload in enumerate(bodies):
                event = IntegrationEvent(
                    source="simulated-upstream",
                    event_id=f"bench:{agent}:{sequence}",
                    occurred_at=dt.datetime.combine(day, dt.time(12), tzinfo=dt.UTC),
                    agent_id=str(agent),
                    payload=payload,
                )
                integration.submit(event, "benchmark")
        ingestion_seconds = elapsed(start)
        start = time.perf_counter()
        while integration.process_one():
            pass
        projection_seconds = elapsed(start)
        with store.operations.connect() as db:
            failures = db.execute(
                "SELECT COUNT(*) FROM integration_events WHERE status<>'processed'"
            ).fetchone()[0]
            projections = {
                r[0]: r[1:]
                for r in db.execute(
                    "SELECT agent_id,cashin,cashout,denied_cashin,denied_cashout FROM integration_days"
                )
            }
        if failures:
            raise RuntimeError(f"Benchmark had {failures} unprocessed events")
        feature_seconds, inference_seconds = 0.0, 0.0
        co, ci = [], []
        for first in range(0, count, batch_size):
            last = min(count, first + batch_size)
            indices, ids = store.indices[first:last], store.ids[first:last]
            start = time.perf_counter()
            m = Matrices(
                ids,
                base.m.dates,
                {s: a[indices].copy() for s, a in base.m.y.items()},
                {s: a[indices].copy() for s, a in base.m.demand.items()},
                {s: a[indices].copy() for s, a in base.m.stockout.items()},
            )
            for offset, agent in enumerate(ids):
                cashin, cashout, denied_ci, denied_co = projections[agent]
                m.y["cashin"][offset, t], m.y["cashout"][offset, t] = cashin, cashout
                m.stockout["cashin"][offset, t], m.stockout["cashout"][offset, t] = (
                    bool(denied_ci),
                    bool(denied_co),
                )
            panel = build_panel(base.cfg, m, base.calendar, store.agents.iloc[first:last], np.array([t]))
            feature_seconds += time.perf_counter() - start
            start = time.perf_counter()
            co.append(
                base.models.predict_amount(panel, "cashout").reshape(
                    last - first, base.cfg.model.horizons, 3
                )[:, 0]
            )
            ci.append(
                base.models.predict_amount(panel, "cashin").reshape(last - first, base.cfg.model.horizons, 3)[
                    :, 0
                ]
            )
            inference_seconds += time.perf_counter() - start
        start = time.perf_counter()
        rec = recommend(
            base.params(),
            base.close_cash[store.indices, t],
            base.close_efloat[store.indices, t],
            store.capacity,
            np.concatenate(co),
            np.concatenate(ci),
        )
        visits = 0
        for _, group in store.agents.groupby("dso_id"):
            ix = group.index.to_numpy()
            policy = base.cfg.policy.dso
            plan = PLANNERS[policy.allocator](
                rec["action"][ix],
                rec["cash_delta"][ix],
                rec["expected_shortfall"][ix],
                policy.max_visits,
                policy.max_cash,
            )
            visits += len(plan.visits)
        planning_seconds = elapsed(start)
        total = (
            ingestion_seconds + projection_seconds + feature_seconds + inference_seconds + planning_seconds
        )
        return {
            "agents": count,
            "events": count * 4,
            "failed_events": failures,
            "ingestion_seconds": ingestion_seconds,
            "projection_seconds": projection_seconds,
            "feature_seconds": round(feature_seconds, 4),
            "inference_seconds": round(inference_seconds, 4),
            "planning_seconds": planning_seconds,
            "total_seconds": round(total, 4),
            "ingestion_events_per_second": round(count * 4 / max(ingestion_seconds, 1e-9), 2),
            "planned_visits": visits,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--populations", nargs="+", type=int, default=[500, 10000, 50000])
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args()
    if any(n < 1 or n > 99999 for n in args.populations) or args.batch_size < 1:
        parser.error("populations must be 1..99999 and batch size must be positive")
    cfg = get_config()
    base = Store(cfg)
    rows = []
    for count in args.populations:
        row = measure(base, count, args.batch_size)
        rows.append(row)
        print(json.dumps(row), flush=True)
    report = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "hardware": platform.platform(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "model": base.models.version,
        "synthetic": True,
        "batch_size": args.batch_size,
        "limits": "Sequential local ingestion; replicated synthetic histories; excludes HTTP, concurrent clients, ingestion broker, and model retraining.",
        "results": rows,
    }
    output = cfg.artifacts_dir / "integration_benchmark.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved measured results to {output}")


if __name__ == "__main__":
    main()
