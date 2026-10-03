"""API smoke and contract tests against the sample data and tiny models (R-CODE-4, R-SEC-2/3)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from floatwise.api.main import create_app
from floatwise.api.store import Store

P = "/api/v1"


@pytest.fixture(scope="module")
def client(tiny_cfg, cfg, tiny_artifacts):
    api_cfg = tiny_cfg.with_overrides(paths={"data_dir": str(cfg.sample_dir)})
    with TestClient(create_app(api_cfg, Store(api_cfg))) as c:
        yield c


@pytest.fixture(scope="module")
def agent_id(client):
    agents = client.get(f"{P}/agents").json()
    return max(agents, key=lambda a: a["p_stockout"])["agent_id"]


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def test_health(client, cfg):
    h = client.get(f"{P}/health").json()
    assert h["status"] == "ok" and h["demo_date"] == str(cfg.dates.demo_date)


def test_agents_list_and_filters(client):
    all_agents = client.get(f"{P}/agents").json()
    assert len(all_agents) == 50
    assert {"agent_id", "risk_band", "action", "amount", "lat", "lon"} <= all_agents[0].keys()
    risky = client.get(f"{P}/agents", params={"risk_min": 0.5}).json()
    assert all(a["p_stockout"] >= 0.5 for a in risky)
    garment = client.get(f"{P}/agents", params={"archetype": "garment_belt"}).json()
    assert garment and all(a["archetype"] == "garment_belt" for a in garment)


def test_agent_detail_forecast_recommendation(client, agent_id):
    d = client.get(f"{P}/agents/{agent_id}").json()
    assert 1 <= len(d["history"]) <= 28 and d["agent"]["agent_id"] == agent_id
    f = client.get(f"{P}/agents/{agent_id}/forecast").json()
    assert len(f["points"]) == 7
    for pt in f["points"]:
        assert pt["cashout"]["p10"] <= pt["cashout"]["p50"] <= pt["cashout"]["p90"]
    r = client.get(f"{P}/agents/{agent_id}/recommendation").json()
    assert r["action"] in {"TOP_UP_CASH", "TOP_UP_EFLOAT", "NO_ACTION", "NEEDS_EXTRA_FLOAT"}
    assert r["amount"] % 1000 == 0 and len(r["outlook"]) == 7
    assert any(code.startswith("EID_FITR_IN_") for code in r["reason_codes"])  # demo date is pre-Eid


@pytest.mark.parametrize("lang", ["bn", "en"])
def test_explanation_never_errors(client, agent_id, lang):
    e = client.get(f"{P}/agents/{agent_id}/explanation", params={"lang": lang}).json()
    assert e["source"] in {"template", "cache"} and len(e["narrative"]) > 20
    assert len(e["drivers"]) == 5


def test_dso_plan_respects_capacity(client):
    dsos = client.get(f"{P}/dsos").json()
    dso = max(dsos, key=lambda x: x["n_at_risk"])["dso_id"]
    plan = client.get(f"{P}/dso/{dso}/plan", params={"max_visits": 2, "max_cash": 300000}).json()
    assert len(plan["visits"]) <= 2 and plan["cash_to_carry"] <= 300000
    assert [v["rank"] for v in plan["visits"]] == list(range(1, len(plan["visits"]) + 1))


def test_network_summary(client):
    s = client.get(f"{P}/network/summary").json()
    assert sum(s["by_band"].values()) == s["n_agents"] == 50
    assert s["upcoming_events"][0]["name"] == "Eid-ul-Fitr"


def test_simulate_cached_and_live(client):
    cached = client.post(f"{P}/simulate", json={}).json()
    assert cached["source"] == "cache"
    live = client.post(f"{P}/simulate", json={"service_level": 0.9, "max_visits": 5}).json()
    assert live["source"] == "live" and live["params"]["service_level"] == 0.9


def test_metrics_endpoint(client):
    m = client.get(f"{P}/metrics/model").json()
    assert "test" in m["metrics"] and "assumptions" in m


def test_decisions_roundtrip(client, agent_id):
    body = {"agent_id": agent_id, "date": "2026-03-15", "action": "TOP_UP_CASH", "recommended_amount": 50000,
            "final_amount": 40000, "decision": "modify", "reason": "DSO carries less cash today"}  # fmt: skip
    r = client.post(f"{P}/decisions", json=body)
    assert r.status_code == 200 and r.json()["decided_at"]
    assert client.get(f"{P}/decisions").json()[-1]["final_amount"] == 40000


@pytest.mark.parametrize(
    ("method", "url", "body", "status", "code"),
    [
        ("get", f"{P}/agents/AG99999", None, 404, "not_found"),
        ("get", f"{P}/network/summary?date=2020-01-01", None, 422, "date_out_of_range"),
        ("get", f"{P}/agents/AG00001/forecast?horizon=30", None, 422, "invalid_request"),
        ("post", f"{P}/decisions", {"agent_id": "x; DROP", "date": "2026-03-15", "action": "TOP_UP_CASH",
                                     "recommended_amount": 1, "final_amount": 1, "decision": "approve"}, 422,
         "invalid_request"),
        ("post", f"{P}/simulate", {"service_level": 5}, 422, "invalid_request"),
    ],
)  # fmt: skip
def test_errors_use_standard_shape(client, method, url, body, status, code):
    r = client.post(url, json=body) if method == "post" else client.get(url)
    assert r.status_code == status
    assert r.json()["error"]["code"] == code and "Traceback" not in r.text


def test_cors_is_not_wildcard(client):
    ok = client.get(f"{P}/health", headers={"Origin": "http://localhost:5173"})
    bad = client.get(f"{P}/health", headers={"Origin": "https://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers
