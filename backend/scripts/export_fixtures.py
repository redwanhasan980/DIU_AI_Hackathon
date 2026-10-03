"""Export API responses for the demo date into frontend/src/fixtures/ (RULES.md R-API-2).

The web app falls back to these files when the API is unreachable, so the main demo path still renders
offline. File names mirror the request path (see frontend/src/api/client.ts `fixtureFor`).
Run after `make all`: python scripts/export_fixtures.py
"""

from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

from floatwise.api.main import create_app
from floatwise.config import REPO_ROOT, get_config

DEMO_AGENT = "AG00471"  # Rahmania Bhandar, Sylhet — rural remittance agent for the pitch walkthrough


def key(path: str) -> str:
    return re.sub(r"[/?=&]", "_", path.lstrip("/"))


def main() -> None:
    cfg = get_config()
    d = str(cfg.dates.demo_date)
    out = REPO_ROOT / "frontend" / "src" / "fixtures"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.json"):
        f.unlink()
    with TestClient(create_app()) as c:
        dsos = c.get(f"/api/v1/dsos?date={d}").json()
        busiest = max(dsos, key=lambda x: x["n_at_risk"])["dso_id"]
        k, m = cfg.policy.dso.max_visits, cfg.policy.dso.max_cash
        paths = [
            "/health",
            "/metrics/model",
            "/decisions",
            "/decisions/summary",
            f"/network/summary?date={d}",
            f"/agents?date={d}",
            f"/dsos?date={d}",
            f"/dso/{busiest}/plan?date={d}&max_visits={k}&max_cash={m}",
            f"/agents/{DEMO_AGENT}?date={d}",
            f"/agents/{DEMO_AGENT}/forecast?date={d}",
            f"/agents/{DEMO_AGENT}/recommendation?date={d}",
            f"/agents/{DEMO_AGENT}/explanation?date={d}&lang=bn",
            f"/agents/{DEMO_AGENT}/explanation?date={d}&lang=en",
        ]
        for p in paths:
            r = c.get("/api/v1" + p)
            r.raise_for_status()
            body = r.json() if p != "/decisions" else []  # demo starts with an empty log
            (out / f"{key(p)}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        sim = c.post("/api/v1/simulate", json={})
        (out / "simulate.json").write_text(json.dumps(sim.json(), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(paths) + 1} fixtures to {out}")


if __name__ == "__main__":
    main()
