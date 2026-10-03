"""Grounded LLM narrative with guardrails (FR-XAI-2/3, R-AI-1..3).

The model only rephrases a structured `facts` dict built by our code. It never computes amounts.
Every number in its output must already appear in the facts (numeric post-check); any failure —
no key, timeout, API error, refusal, truncation, or a new number — falls back to the template.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

import anthropic

from floatwise.config import Config
from floatwise.explain import labels as L
from floatwise.explain.templates import render

log = logging.getLogger(__name__)

SYSTEM = """You write short explanations for mobile-money agents and field officers in Bangladesh.
You receive a JSON object of facts about one agent's cash or e-float recommendation.
Rules:
- Use ONLY the facts given. Do not add, compute, round or convert any number; copy amounts, dates and
  percentages exactly as written in the facts.
- Write in the language named in `language` (Bangla in Bangla script, or English).
- At most 3 short sentences, warm and practical, plain words for a shopkeeper. No markdown, no lists.
- Say what to do (from `action_label` and `amount`) and why (from the event and `top_drivers`).
- If `action` is NO_ACTION, reassure and mention `risk_rises_on` only if present."""

_NUM = re.compile(r"[0-9০-৯][0-9০-৯,]*(?:\.[0-9০-৯]+)?")


@dataclass
class NarrativeResult:
    text: str
    source: str  # "llm" | "template"


def numbers_in(text: str) -> set[str]:
    """Normalised numbers in a text: Bangla digits -> ASCII, grouping commas removed."""
    out = set()
    for m in _NUM.findall(text.translate(L.ASCII_DIGITS)):
        n = m.replace(",", "").rstrip(".")
        if n:
            out.add(n.lstrip("0") or "0")
    return out


def passes_numeric_check(output: str, facts: dict) -> bool:
    allowed = numbers_in(json.dumps(facts, ensure_ascii=False))
    return numbers_in(output) <= allowed


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _model(cfg: Config) -> str:
    return os.environ.get(cfg.llm.model_env) or cfg.llm.default_model


def generate(
    cfg: Config, facts: dict, lang: str, client: anthropic.Anthropic | None = None
) -> NarrativeResult:
    template = NarrativeResult(render(facts, lang), "template")
    if client is None:
        if not llm_available():
            return template
        client = anthropic.Anthropic(timeout=cfg.llm.timeout_s, max_retries=1)
    try:
        response = client.beta.messages.create(
            model=_model(cfg),
            max_tokens=cfg.llm.max_tokens,
            system=SYSTEM,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
        )
    except anthropic.APIConnectionError as e:  # includes timeouts
        log.warning("LLM unreachable, using template: %s", e)
        return template
    except anthropic.RateLimitError:
        log.warning("LLM rate limited, using template")
        return template
    except anthropic.APIStatusError as e:
        log.warning("LLM error %s, using template", e.status_code)
        return template

    if response.stop_reason in ("refusal", "max_tokens"):
        log.warning("LLM stop_reason=%s, using template", response.stop_reason)
        return template
    text = " ".join(b.text for b in response.content if b.type == "text").strip()
    if not text or not passes_numeric_check(text, facts):
        log.warning("LLM output failed the numeric check, using template")
        return template
    return NarrativeResult(text, "llm")
