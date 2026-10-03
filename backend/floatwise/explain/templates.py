"""Deterministic Bangla/English explanation (FR-XAI-4). Always works — the LLM's fallback.

Input is the same `facts` dict the LLM receives (built by `facts()`), so both paths describe the
same numbers. Every number in `facts` is pre-formatted text; templates only arrange it.
"""

from __future__ import annotations

import datetime as dt

from floatwise.explain import labels as L


def facts(
    rec: dict, agent: dict, drivers: list[dict], event: tuple[str, dt.date, int] | None, lang: str
) -> dict:
    """Structured, pre-formatted facts for one recommendation (the only LLM input, R-AI-2)."""
    side_cash = rec["action"] != "TOP_UP_EFLOAT"
    out = {
        "language": "Bangla" if lang == "bn" else "English",
        "shop_name": agent["shop_name"],
        "area_type": L.ARCHETYPES[agent["archetype"]][lang],
        "location": f"{agent['upazila']}, {agent['district']}",
        "for_date": L.date_str(rec["effective_date"], lang),
        "action": rec["action"],
        "action_label": L.ACTIONS[rec["action"]][lang],
        "amount": L.taka(rec["amount"], lang),
        "balance_type": ("cash" if side_cash else "e-float")
        if lang == "en"
        else ("নগদ" if side_cash else "ই-ফ্লোট"),
        "current_balance": L.taka(rec["open_cash"] if side_cash else rec["open_efloat"], lang),
        "expected_demand": L.taka(round(rec["demand_p50"], -3), lang),
        "high_demand": L.taka(round(rec["demand_p90"], -3), lang),
        "stockout_risk": L.pct(rec["p_stockout"], lang),
        # reasons that push demand up (negative SHAP drivers lower it and are shown only in the UI)
        "top_drivers": [d["label"] for d in drivers if d["contribution_bdt"] > 0][:3],
    }
    if event is not None:
        out["upcoming_event"] = L.EVENTS.get(event[0], {"en": event[0], "bn": event[0]})[lang]
        out["days_to_event"] = L.num(event[2], lang)
    if rec.get("first_risk_date") and rec["action"] == "NO_ACTION":
        out["risk_rises_on"] = L.date_str(rec["first_risk_date"], lang)
    return out


def render(f: dict, lang: str) -> str:
    return _BN(f) if lang == "bn" else _EN(f)


def _EN(f: dict) -> str:
    parts = []
    if "upcoming_event" in f:
        parts.append(f"{f['upcoming_event']} is {f['days_to_event']} days away.")
    parts.append(
        f"On {f['for_date']}, {f['shop_name']} is expected to need about {f['expected_demand']} "
        f"in {f['balance_type']} transactions (up to {f['high_demand']} on a busy day), "
        f"while it holds {f['current_balance']} — a {f['stockout_risk']} chance of running out."
    )
    a = f["action"]
    if a == "TOP_UP_CASH":
        parts.append(f"Recommended: bring {f['amount']} in cash before opening.")
    elif a == "TOP_UP_EFLOAT":
        parts.append(f"Recommended: convert {f['amount']} of cash into e-float before opening.")
    elif a == "NEEDS_EXTRA_FLOAT":
        parts.append(
            f"The shop's total float is about {f['amount']} short of covering both sides — "
            "please escalate to the distributor for extra float."
        )
    else:
        parts.append("Current balances are enough; no action needed.")
        if "risk_rises_on" in f:
            parts.append(f"Watch out: risk rises around {f['risk_rises_on']}.")
    if f["top_drivers"]:
        parts.append("Main reasons: " + "; ".join(f["top_drivers"]) + ".")
    return " ".join(parts)


def _BN(f: dict) -> str:
    parts = []
    if "upcoming_event" in f:
        parts.append(f"{f['upcoming_event']} আর {f['days_to_event']} দিন বাকি।")
    parts.append(
        f"{f['for_date']} তারিখে {f['shop_name']}-এ প্রায় {f['expected_demand']} {f['balance_type']} লেনদেনের "
        f"চাহিদা হতে পারে (ব্যস্ত দিনে {f['high_demand']} পর্যন্ত), কিন্তু এখন আছে {f['current_balance']} — "
        f"ফুরিয়ে যাওয়ার সম্ভাবনা {f['stockout_risk']}।"
    )
    a = f["action"]
    if a == "TOP_UP_CASH":
        parts.append(f"পরামর্শ: দোকান খোলার আগে {f['amount']} নগদ টাকা এনে রাখুন।")
    elif a == "TOP_UP_EFLOAT":
        parts.append(f"পরামর্শ: দোকান খোলার আগে {f['amount']} নগদ টাকা ই-ফ্লোটে রূপান্তর করুন।")
    elif a == "NEEDS_EXTRA_FLOAT":
        parts.append(f"দোকানের মোট ফ্লোটে প্রায় {f['amount']} ঘাটতি — অতিরিক্ত ফ্লোটের জন্য ডিস্ট্রিবিউটরকে জানান।")
    else:
        parts.append("বর্তমান ব্যালেন্সই যথেষ্ট; কোনো পদক্ষেপ লাগবে না।")
        if "risk_rises_on" in f:
            parts.append(f"সতর্কতা: {f['risk_rises_on']} নাগাদ ঝুঁকি বাড়বে।")
    if f["top_drivers"]:
        parts.append("মূল কারণ: " + "; ".join(f["top_drivers"]) + "।")
    return " ".join(parts)
