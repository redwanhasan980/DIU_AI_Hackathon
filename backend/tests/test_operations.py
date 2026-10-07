"""Security boundaries, concurrent persistence and live inference using synthetic fixtures."""

from __future__ import annotations

import datetime as dt
import json
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from floatwise.api.main import create_app
from floatwise.api.persistence import Conflict, OperationsDB
from floatwise.api.security import AccessControl
from floatwise.api.store import Store
from floatwise.models.calibration import IntervalCalibrator


def test_concurrent_decisions_are_durable_and_idempotent(tmp_path):
    path = tmp_path / "operations.sqlite3"
    first, second = OperationsDB(path), OperationsDB(path)

    def write(i):
        db = first if i % 2 else second
        item = {
            "agent_id": "AG00001",
            "decision": "approve",
            "final_amount": i,
            "decided_at": str(dt.datetime.now(dt.UTC)),
        }
        return db.add_decision(item, "synthetic-operator", str(i))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(40)))
    reopened = OperationsDB(path)
    assert len(reopened.decisions()) == len(reopened.audit_events()) == 40
    item = reopened.decisions()[0]
    replay = {**item, "decided_at": "a later timestamp"}
    assert reopened.add_decision(replay, "synthetic-operator", str(item["final_amount"])) == item
    with pytest.raises(Conflict):
        reopened.add_decision({**item, "final_amount": 999}, "synthetic-operator", str(item["final_amount"]))
    assert len(reopened.decisions()) == 40


def test_balance_compare_and_swap_across_connections(tmp_path):
    path = tmp_path / "operations.sqlite3"
    stores = [OperationsDB(path), OperationsDB(path)]
    day = dt.date(2026, 3, 15)

    def write(db):
        try:
            db.set_balance("AG00001", day, 2000, 3000, 0, "synthetic-admin")
            return True
        except Conflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, stores)) == [False, True]
    assert OperationsDB(path).balance("AG00001", day) == {"version": 1, "cash": 2000, "efloat": 3000}


def test_decision_rejects_concurrent_balance_revision_and_replays_after_revision(tmp_path):
    db = OperationsDB(tmp_path / "operations.sqlite3")
    day = dt.date(2026, 3, 15)
    body = {"agent_id": "AG00001", "date": str(day), "balance_version": 0, "decision": "approve"}
    first = db.add_decision(body, "synthetic-operator", "one")
    db.set_balance("AG00001", day, 2000, 3000, 0, "synthetic-admin")
    with pytest.raises(Conflict):
        db.add_decision(body, "synthetic-operator", "two")
    assert db.replay_decision(body, "synthetic-operator", "one") == first


def test_required_decisions_check_server_recommendation(secured_client):
    client, store = secured_client
    agent = str(store.agents.iloc[1]["agent_id"])
    day = str(store.cfg.dates.demo_date)
    rec = client.get(f"/api/v1/agents/{agent}/recommendation?date={day}", headers=headers("operator")).json()
    body = {
        "agent_id": agent,
        "date": day,
        "action": rec["action"],
        "recommended_amount": rec["amount"],
        "final_amount": 0,
        "decision": "reject",
        "balance_version": rec["balance_version"],
    }
    assert client.post("/api/v1/decisions", json=body, headers=headers("operator")).status_code == 200
    invalid = {**body, "recommended_amount": rec["amount"] + 1}
    assert client.post("/api/v1/decisions", json=invalid, headers=headers("operator")).status_code == 409


def test_authentication_fails_closed(monkeypatch):
    monkeypatch.setenv("FLOATWISE_AUTH_MODE", "required")
    monkeypatch.delenv("FLOATWISE_CREDENTIALS", raising=False)
    with pytest.raises(ValueError):
        AccessControl()
    monkeypatch.setenv("FLOATWISE_AUTH_MODE", "demo")
    control = AccessControl()
    assert control.authenticate("", "127.0.0.1") is not None
    assert control.authenticate("", "203.0.113.1") is None


@pytest.fixture
def secured_client(tiny_cfg, cfg, tiny_artifacts, monkeypatch):
    monkeypatch.setenv("FLOATWISE_AUTH_MODE", "required")
    monkeypatch.setenv(
        "FLOATWISE_CREDENTIALS",
        json.dumps(
            [
                {"subject": role, "role": role, "token": role.ljust(40, "x")}
                for role in ("viewer", "operator", "admin")
            ]
        ),
    )
    api_cfg = tiny_cfg.with_overrides(paths={"data_dir": str(cfg.sample_dir)})
    store = Store(api_cfg)
    with TestClient(create_app(api_cfg, store)) as client:
        yield client, store


def headers(role):
    return {"Authorization": f"Bearer {role.ljust(40, 'x')}"}


def test_roles_limit_operational_access(secured_client):
    client, _ = secured_client
    assert client.get("/api/v1/agents").status_code == 401
    assert client.get("/api/v1/agents", headers=headers("viewer")).status_code == 200
    assert client.post("/api/v1/decisions", json={}, headers=headers("viewer")).status_code == 403
    assert client.get("/api/v1/operations/audit", headers=headers("operator")).status_code == 403
    audit = client.get("/api/v1/operations/audit", headers=headers("admin"))
    assert audit.status_code == 200
    assert any(e["event"] == "authorization_denied" for e in audit.json())
    assert "Bearer" not in audit.text and "xxxxxxxx" not in audit.text
    denied = client.get("/api/v1/agents", headers={"Origin": "http://localhost:5173"})
    assert denied.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_live_inference_and_balance_recalculation(secured_client, monkeypatch):
    client, store = secured_client
    agent = str(store.agents.iloc[0]["agent_id"])
    day = str(store.cfg.dates.demo_date)
    # Force cached forecasts to be nonsense: the live route must execute boosters instead.
    original = store.F.copy()
    monkeypatch.setattr(store, "F", np.zeros_like(store.F))
    live = client.post(
        "/api/v1/operations/forecast", json={"agent_id": agent, "date": day}, headers=headers("admin")
    )
    assert live.status_code == 200 and live.json()["source"] == "live"
    assert live.json()["points"][0]["cashout"]["p50"] > 0
    monkeypatch.setattr(store, "F", original)
    b = client.get(f"/api/v1/operations/balances/{agent}?date={day}", headers=headers("admin")).json()
    cap = b["cash"] + b["efloat"]
    body = {"agent_id": agent, "date": day, "cash": 0, "efloat": cap, "expected_version": b["version"]}
    changed = client.post("/api/v1/operations/balances", json=body, headers=headers("admin"))
    assert changed.status_code == 200
    assert client.post("/api/v1/operations/balances", json=body, headers=headers("admin")).status_code == 409
    rec = client.get(f"/api/v1/agents/{agent}/recommendation?date={day}", headers=headers("viewer")).json()
    assert rec["open_cash"] == 0 and rec["open_efloat"] == cap
    assert rec["p_cash_stockout"] > 0
    assert Store(store.cfg).balance(agent, store.cfg.dates.demo_date)["cash"] == 0
    invalid = {**body, "efloat": cap + 1, "expected_version": b["version"] + 1}
    assert (
        client.post("/api/v1/operations/balances", json=invalid, headers=headers("admin")).status_code == 422
    )


def test_rate_limits_and_body_limits(secured_client):
    client, store = secured_client
    response = client.post(
        "/api/v1/simulate", content="x" * (store.cfg.api.max_body_bytes + 1), headers=headers("operator")
    )
    assert response.status_code == 413
    # A shared database enforces the budget even across independent API workers.
    for _ in range(store.cfg.api.requests_per_minute):
        store.operations.allow_request("viewer", int(time.time() // 60), store.cfg.api.requests_per_minute)
    limited = client.get("/api/v1/agents", headers=headers("viewer"))
    assert limited.status_code == 429 and limited.headers["Retry-After"] == "60"


def test_conformal_expansion_ignores_censored_labels_and_preserves_median():
    panel = pd.DataFrame(
        {
            "days_to_eid_fitr": [2] * 5,
            "days_to_eid_adha": [100] * 5,
            "days_after_eid": [100] * 5,
            "h": [1] * 5,
            "scale_cashout": [100.0] * 5,
            "served_cashout": [100.0, 150.0, 200.0, 250.0, 999999.0],
            "censored_cashout": [0, 0, 0, 0, 1],
        }
    )
    pred = np.tile([50.0, 100.0, 150.0], (5, 1))
    cal = IntervalCalibrator.fit(panel, {"cashout": pred}, (-7, 3), 0.8, 2)
    adjusted = cal.apply(panel, pred, "cashout")
    assert cal.adjustments["cashout:1:1"]["n"] == 4
    assert np.all(adjusted[:, 1] == pred[:, 1])
    assert np.all(adjusted[:, 0] <= adjusted[:, 1]) and np.all(adjusted[:, 1] <= adjusted[:, 2])
    assert np.all(adjusted[:, 2] == 250.0)
