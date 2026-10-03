"""Pre-generate LLM explanations for the demo so the demo works offline (FR-XAI-5).

Picks the highest-priority agents of each area type on the demo date plus every agent in the
busiest DSO plan, asks the LLM for Bangla and English explanations (with the numeric guardrail),
and stores the accepted ones in artifacts/narratives_cache.json. Without an API key it does nothing:
the API then uses the deterministic templates.  Run: python scripts/build_narratives.py
"""

from __future__ import annotations

import json

import numpy as np

from floatwise.api.main import load_env_file
from floatwise.api.store import Store
from floatwise.config import get_config
from floatwise.explain.llm import llm_available


def main() -> None:
    load_env_file()
    cfg = get_config()
    if not llm_available():
        print("no ANTHROPIC_API_KEY: skipping (explanations will use the Bangla/English templates)")
        return
    store = Store(cfg)
    d = cfg.dates.demo_date
    rec = store.network_rec(d)
    agents = store.agents
    picked: list[str] = []
    for arch in cfg.archetypes:
        idx = agents.index[agents["archetype"] == arch].to_numpy()
        top = idx[np.argsort(-rec["expected_shortfall"][idx])][: cfg.llm.demo_agents_per_archetype]
        picked += list(agents.loc[top, "agent_id"])
    busiest = max(store.dsos(d), key=lambda x: x["n_at_risk"])["dso_id"]
    picked += [v["agent_id"] for v in store.dso_plan(busiest, d, None, None)["visits"]]

    counts = {"llm": 0, "template": 0}
    for agent_id in dict.fromkeys(picked):
        for lang in ("bn", "en"):
            out = store.explanation(agent_id, d, lang)
            counts[out["source"] if out["source"] != "cache" else "llm"] += 1
    path = cfg.artifacts_dir / "narratives_cache.json"
    path.write_text(json.dumps(store.narrative_cache, indent=2, ensure_ascii=False))
    print(f"{len(store.narrative_cache)} cached narratives -> {path} ({counts})")


if __name__ == "__main__":
    main()
