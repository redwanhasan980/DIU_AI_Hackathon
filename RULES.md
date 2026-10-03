# FloatWise — Project Rules

These rules are **mandatory** for every human and every AI agent working in this repo. When a rule conflicts with speed, the rule wins. If a rule blocks you, raise it with the team instead of quietly breaking it.

Rule IDs are referenced from `docs/SRS.md` and `docs/IMPLEMENTATION_PLAN.md`.

---

## 1. Data & Privacy

- **R-DATA-1:** Use only synthetic, public or self-generated data. Never add real customer, agent or transaction data, real phone numbers, NIDs or real people's names.
- **R-DATA-2:** Synthetic shop names must be generic (e.g. "Mayer Doa Telecom"). Do not use real business names.
- **R-DATA-3:** Every synthetic assumption (multipliers, base amounts, Eid dates, fees) lives in `config.yaml` **and** is explained in `docs/DATA_ASSUMPTIONS.md`. No magic numbers in code.
- **R-DATA-4:** Generation is deterministic from the seed in config. The same seed must give the same files.
- **R-DATA-5:** Never commit generated full datasets or model binaries. Only `data/sample/` (≤ 5 MB) and small JSON artifacts needed for the offline demo may be committed.

## 2. Machine Learning

- **R-ML-1:** Split **by time only** (dates in config). The test period (2026-01-01 → 2026-06-30) is touched only for the final evaluation and the backtest. Never tune on it.
- **R-ML-2:** No leakage. Features for origin date `t` may use data ≤ `t` only. Calendar features of the target date are allowed (known in advance). `tests/test_no_leakage.py` must stay green.
- **R-ML-3:** Every model is compared to the baselines (seasonal-naive, trailing-7-day mean). A model that doesn't beat a baseline is not "better", whatever it looks like.
- **R-ML-4:** Quantile outputs must be non-crossing (P10 ≤ P50 ≤ P90).
- **R-ML-5:** Report real numbers. Never inflate, cherry-pick or hand-edit metrics. Every number shown in the UI, deck or README must come from `artifacts/*.json` produced by code.
- **R-ML-6:** Ground-truth columns (`*_demand_amt`) are for evaluation and simulation only. They are **never** model features.

## 3. Decisions, LLM & Responsible AI

- **R-AI-1:** Money amounts, risk scores and actions are computed by deterministic code from model outputs (`engine/`). **The LLM never computes or decides amounts.**
- **R-AI-2:** The LLM receives only structured JSON produced by our code, never free text from users. The prompt says to use only the provided facts.
- **R-AI-3:** Every LLM output passes the numeric post-check (all numbers must exist in the input). On failure, timeout or missing key, fall back to the deterministic template. The explanation endpoint must never error.
- **R-AI-4:** No automatic money movement. Every recommendation needs explicit human Approve / Modify / Reject. `NEEDS_EXTRA_FLOAT` always escalates to a human.
- **R-AI-5:** The UI must label AI-generated text as "AI-generated explanation", and must show predictions, assumptions and generated text as visually distinct.
- **R-AI-6:** No credit, lending or penalty decisions about agents. FloatWise is an operational liquidity tool only.
- **R-AI-7:** Fairness is checked per archetype and for rural vs urban before the demo. A segment worse than the baseline must be reported, not hidden.

## 4. Security

- **R-SEC-1:** Secrets only in `.env` (git-ignored). `.env.example` holds empty placeholders. Before every push, `git grep -iE "sk-ant|api_key\s*=\s*['\"][^'\"]+"` must return nothing.
- **R-SEC-2:** Validate all API inputs with pydantic; return the standard error format; never leak stack traces to clients.
- **R-SEC-3:** CORS is restricted to the frontend origin (configurable), not `*`, in demo mode.
- **R-SEC-4:** No new third-party service calls beyond the LLM API without a team decision. The demo must work offline.

## 5. Code Quality

- **R-CODE-1:** Layering: `data/` → `features/` → `models/` → `engine/` → `simulation/` / `explain/` → `api/`. Lower layers never import higher ones. Business rules live only in `engine/`.
- **R-CODE-2:** Python: type hints on public functions; `ruff` clean; functions small and pure where possible; config passed in, not read from globals deep in the code.
- **R-CODE-3:** TypeScript: `strict` mode; API types in `src/api/types.ts` mirror `backend/floatwise/schemas.py`; no `any` in API code.
- **R-CODE-4:** Tests are required for: data quality, leakage, engine (risk/recommend/allocate), LLM fallback/post-check, and API smoke tests. `make test` must be green before every push to the shared branch.
- **R-CODE-5:** No dead experiments in `backend/floatwise/`. Notebooks and scratch go in `notebooks/` (not imported by the app).
- **R-CODE-6:** Money is handled in whole taka (int). Display uses Bangladeshi grouping `৳1,20,000`. Recommendations are rounded up to ৳1,000.
- **R-CODE-7:** All text files are UTF-8. Bangla strings live in translation maps (`explain/labels.py`, `frontend/src/i18n/`), not scattered through the code.

## 6. Interfaces & Contracts

- **R-API-1:** The schemas in `docs/SRS.md` §5.1 and §8, and `schemas.py`, are contracts. Changing one requires updating the SRS, the backend schemas, the frontend types and the fixtures **in the same commit**, and telling the team.
- **R-API-2:** The frontend must keep working from `src/fixtures/` when the API is down (dev mode).

## 7. Git & Workflow

- **R-GIT-1:** Small commits, one task each, with an imperative message prefixed by area: `data: add Eid multipliers`, `engine: greedy DSO allocation`, `web: agent detail chart`, `docs: …`.
- **R-GIT-2:** Tick the matching checkbox in `docs/IMPLEMENTATION_PLAN.md` in the same commit that completes the task.
- **R-GIT-3:** Pull/rebase before starting a task; never force-push a shared branch.
- **R-GIT-4:** Never commit `.env`, `data/generated/`, `artifacts/models/`, `node_modules/` or `.venv/`.

## 8. Time-boxing & Scope

- **R-TIME-1:** P0 before P1 before P2. No P2 work while any P0 item is open.
- **R-TIME-2:** Stuck for more than 30 minutes → take the fallback in `IMPLEMENTATION_PLAN.md` ("Risk Fallbacks") or ask the team.
- **R-TIME-3:** **Feature freeze at H+18.** After that, only bug fixes, polish, docs and rehearsal.
- **R-TIME-4:** Never break the demo path. Before merging anything after H+12, run through the SRS §14 demo script.

## 9. Definition of Done (every task)

1. The code works for the demo date (2026-03-15) and the sample data.
2. Tests were added or updated, and `make test` + `make lint` are green.
3. Any new assumption is in config and `DATA_ASSUMPTIONS.md`.
4. The checkbox is ticked in the implementation plan.
5. Committed with an area-prefixed message and pushed.
