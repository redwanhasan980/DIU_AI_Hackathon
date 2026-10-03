"""Explanations: formatting, templates, SHAP drivers and the LLM guardrails (R-AI-1..3)."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import anthropic
import httpx2
import numpy as np
import pytest

from floatwise.explain import labels as L
from floatwise.explain import llm
from floatwise.explain.shap_explain import explain_row
from floatwise.explain.templates import facts, render
from floatwise.features.build import build_panel, to_matrices
from floatwise.models.predict import QuantileModels

# ---- formatting ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "expected"),
    [(999, "999"), (1000, "1,000"), (120000, "1,20,000"), (1234567, "12,34,567"), (-25000, "-25,000")],
)
def test_lakh_grouping(n, expected):
    assert L.lakh(n) == expected


def test_bangla_digits():
    assert L.taka(120000, "bn") == "৳১,২০,০০০"
    assert L.pct(0.64, "bn") == "৬৪%"


# ---- templates -------------------------------------------------------------------


def _facts(action="TOP_UP_CASH", lang="en", amount=179000):
    rec = {
        "action": action, "amount": amount, "open_cash": 62000, "open_efloat": 300000,
        "effective_date": dt.date(2026, 3, 16), "p_stockout": 0.64, "demand_p50": 185400,
        "demand_p90": 240100, "first_risk_date": dt.date(2026, 3, 18),
    }  # fmt: skip
    agent = {"shop_name": "Mayer Doa Telecom", "archetype": "rural_remittance", "upazila": "Beanibazar",
             "district": "Sylhet"}  # fmt: skip
    drivers = [{"label": "Days to Eid-ul-Fitr", "contribution_bdt": 80000},
               {"label": "Day of month", "contribution_bdt": -9000}]  # fmt: skip
    return facts(rec, agent, drivers, ("Eid-ul-Fitr", dt.date(2026, 3, 20), 5), lang)


@pytest.mark.parametrize("action", ["TOP_UP_CASH", "TOP_UP_EFLOAT", "NO_ACTION", "NEEDS_EXTRA_FLOAT"])
@pytest.mark.parametrize("lang", ["en", "bn"])
def test_templates_render_every_action(action, lang):
    text = render(_facts(action, lang), lang)
    assert len(text) > 40
    if action != "NO_ACTION":
        assert L.taka(179000, lang) in text
    assert llm.passes_numeric_check(text, _facts(action, lang))  # templates never invent numbers


def test_facts_only_list_drivers_that_raise_demand():
    f = _facts()
    assert f["top_drivers"] == ["Days to Eid-ul-Fitr"]
    assert f["expected_demand"] == "৳1,85,000"  # rounded to the nearest thousand


# ---- numeric guardrail -----------------------------------------------------------------


def test_numbers_are_normalised_across_scripts():
    assert llm.numbers_in("৳১,২০,০০০ and 64% on 16 March") == {"120000", "64", "16"}


def test_numeric_check_rejects_invented_amount():
    f = _facts()
    assert llm.passes_numeric_check("Bring ৳1,79,000 before opening; Eid is 5 days away.", f)
    assert not llm.passes_numeric_check("Bring ৳2,00,000 before opening.", f)


# ---- LLM path with a fake client -----------------------------------------------------------


class FakeClient:
    def __init__(self, text: str = "", stop_reason: str = "end_turn", exc: Exception | None = None):
        self.calls: list[dict] = []
        self._text, self._stop, self._exc = text, stop_reason, exc
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc:
            raise self._exc
        return SimpleNamespace(
            stop_reason=self._stop, content=[SimpleNamespace(type="text", text=self._text)]
        )


def test_llm_output_used_when_grounded(cfg):
    client = FakeClient("Eid is 5 days away: bring ৳1,79,000 in cash before opening.")
    res = llm.generate(cfg, _facts(), "en", client=client)
    assert res.source == "llm" and "৳1,79,000" in res.text
    call = client.calls[0]
    assert call["model"] == cfg.llm.default_model and "ONLY the facts" in call["system"]
    assert "Mayer Doa Telecom" in call["messages"][0]["content"]  # structured facts only


@pytest.mark.parametrize(
    "client",
    [
        FakeClient("Bring ৳9,99,000 now."),  # invented number
        FakeClient("", stop_reason="refusal"),
        FakeClient("cut off mid sent", stop_reason="max_tokens"),
        FakeClient(
            exc=anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))
        ),
        FakeClient(
            exc=anthropic.InternalServerError(
                "boom", response=httpx2.Response(500, request=httpx2.Request("POST", "https://x")), body=None
            )
        ),
    ],
)
def test_llm_failures_fall_back_to_template(cfg, client):
    res = llm.generate(cfg, _facts(), "en", client=client)
    assert res.source == "template"
    assert res.text == render(_facts(), "en")


def test_no_key_means_template(cfg, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert llm.generate(cfg, _facts(lang="bn"), "bn").source == "template"


# ---- SHAP drivers ------------------------------------------------------------------------------


def test_shap_drivers_add_up_to_the_forecast(tiny_cfg, sample, tiny_artifacts):
    models = QuantileModels.load(tiny_cfg, tiny_artifacts / "models")
    m = to_matrices(sample["daily"])
    t = int(np.where(m.dates == np.datetime64(tiny_cfg.dates.demo_date))[0][0])
    panel = build_panel(
        tiny_cfg, m, sample["calendar"], sample["agents"], np.array([t]), horizons=np.array([1])
    )
    row = panel.iloc[[0]]
    ex = explain_row(tiny_cfg, models, row, "cashout", "en", top=len(models.features))
    total = ex["base_bdt"] + sum(d["contribution_bdt"] for d in ex["drivers"])
    assert abs(total - ex["forecast_p50_bdt"]) <= len(models.features)  # rounding only
    raw = models.boosters[("cashout", 0.5)].predict(row[models.features])[0] * row["scale_cashout"].iloc[0]
    assert ex["forecast_p50_bdt"] == pytest.approx(raw, abs=2)
    assert all(d["label"] and d["value"] for d in ex["drivers"])
