# CLAUDE.md — FloatWise

Guidance for Claude Code (and any AI coding agent) working in this repository.

@RULES.md

## Project in 30 seconds
**FloatWise** is an AI agent-liquidity forecaster for **upay**, built for AI Hackathon 2026 (DIU CPC × upay), Track 05: Merchant & Agent Intelligence.

The problem: MFS agents run out of **cash** (they can't pay cash-outs) or **e-float** (they can't accept cash-ins) around Eid, garment salary days and remittance peaks. FloatWise works in five steps:
1. Forecasts each agent's 1–7-day cash-out/cash-in demand as quantiles.
2. Converts the forecasts into stockout risk and a rebalancing recommendation.
3. Plans DSO visits under capacity limits.
4. Explains each recommendation in Bangla/English.
5. Proves the impact with a backtest against the status-quo policy.

All data is synthetic.

## Source-of-truth documents (read before coding)
| Doc | Use it for |
|---|---|
| `docs/SRS.md` | Requirements (FR-/NFR- IDs), schemas, formulas, API, UI, acceptance criteria |
| `docs/IMPLEMENTATION_PLAN.md` | Task order, owners, checklists, MVP cutline, fallbacks |
| `RULES.md` | Hard rules (imported above). Never violate them |
| `docs/DATA_ASSUMPTIONS.md` | Every synthetic-data assumption (create it in Phase 2) |

When you finish a task, tick its checkbox in `docs/IMPLEMENTATION_PLAN.md` in the same commit.

## Repository layout (target)
```
.
├── CLAUDE.md  RULES.md  README.md  Makefile  .env.example
├── docs/                    SRS.md, IMPLEMENTATION_PLAN.md, DATA_ASSUMPTIONS.md
├── backend/
│   ├── pyproject.toml
│   ├── config.yaml          seed, dates, Eid dates, archetype params, policy & business assumptions
│   ├── floatwise/
│   │   ├── config.py        loads config.yaml → typed settings
│   │   ├── schemas.py       pydantic contracts (mirror of frontend/src/api/types.ts)
│   │   ├── data/            calendar_bd.py, agents.py, demand.py, shocks.py, simulate_status_quo.py, generate.py
│   │   ├── features/        build.py (origin/horizon panel, leakage-safe)
│   │   ├── models/          baselines.py, train.py, evaluate.py, predict.py
│   │   ├── engine/          risk.py, recommend.py, allocate.py   ← ALL business rules live here
│   │   ├── simulation/      backtest.py
│   │   ├── explain/         shap_explain.py, templates.py, llm.py, labels.py
│   │   └── api/             main.py + routers
│   ├── scripts/             plot_data_checks.py, build_narratives.py
│   └── tests/               test_data_quality, test_no_leakage, test_engine, test_explain, test_api
├── frontend/                Vite + React + TS + Tailwind + Recharts + react-leaflet
│   └── src/ api/ (client.ts, types.ts)  fixtures/  pages/  components/  lib/format.ts  i18n/
├── data/
│   ├── sample/              small committed sample for tests
│   └── generated/           full dataset (git-ignored)
└── artifacts/               metrics.json, forecasts.parquet, simulation_default.json,
                             narratives_cache.json, fairness.json, model_card.md  (models/ git-ignored)
```

## Commands (Makefile targets, to be created in Phase 1)
```bash
make setup       # create venv, pip install -e backend[dev]; npm ci in frontend
make data        # generate synthetic data → data/generated/
make train       # train baselines + LightGBM quantile models
make evaluate    # metrics → artifacts/metrics.json, model_card.md
make simulate    # backtest status quo vs FloatWise → artifacts/simulation_default.json
make narratives  # pre-generate bn/en explanations → artifacts/narratives_cache.json
make all         # data train evaluate simulate narratives
make api         # uvicorn floatwise.api.main:app --reload (port 8000)
make web         # vite dev server (port 5173)
make demo        # api + web using cached artifacts, works offline
make test        # pytest backend/tests
make lint        # ruff check backend; tsc --noEmit + eslint in frontend
```
Run a single test: `cd backend && pytest tests/test_engine.py -k recommend -q`.

## Architecture rules of thumb
- **Data flow:** synthetic data → features → ML quantile forecasts → **deterministic engine** (risk, amount, allocation) → SHAP + LLM narrative → API → UI → human approval.
- **The LLM explains; it never decides.** Amounts come from `engine/`. The LLM gets structured JSON only, and its output passes a numeric post-check with a template fallback.
- Precompute forecasts for the test period into `artifacts/forecasts.parquet`. The API reads them so responses stay fast.
- The frontend builds against `src/fixtures/` first, then switches to the real API with `VITE_API_URL`. Contract changes go to SRS + `schemas.py` + `types.ts` + fixtures together.

## Key constants (all live in `backend/config.yaml`; never hard-code them)
- Dates 2024-01-01 → 2026-06-30. Train ≤ 2025-06-30; val 2025-07-01 → 2025-12-31; **test 2026-01-01 → 2026-06-30**.
- **Demo date: 2026-03-15** (Eid-ul-Fitr ≈ 2026-03-20).
- 500 agents, 5 archetypes: `urban_residential`, `garment_belt`, `rural_remittance`, `market_hub`, `university_area`.
- Policy defaults: service level s = 0.99 and risk threshold θ = 0.10 (tuned on validation by `scripts/tune_policy.py`), overlap α = 0.5, min buffer ৳5,000, DSO K = 10 visits, M = ৳10,00,000, app-advice compliance 70 %.
- Censoring mode `inflate` (chosen by `scripts/censoring_experiment.py`).

## Working conventions for agents
- Start every task by reading the relevant SRS section and the plan checklist item. Work on **P0 before P1 before P2**.
- Keep diffs small and in one layer. Don't refactor unrelated code.
- After changes: `make lint && make test`. For data/model changes, also re-run the affected `make` targets and check that `artifacts/metrics.json` still makes sense.
- Never fabricate metrics or results. Numbers in the README, UI and deck must come from `artifacts/*.json`.
- Commit messages: `area: imperative summary` (areas: data, features, models, engine, sim, explain, api, web, docs, build).
- When implementing `explain/llm.py` or anything that calls Claude, load the `claude-api` skill first for current SDK usage and model IDs. Read the model from the env var `LLM_MODEL`, and the key from `ANTHROPIC_API_KEY`.
- Money: integers in taka; display `৳1,20,000` (lakh grouping); round recommendations up to ৳1,000.
- Bangla strings live in `explain/labels.py` (backend) and `frontend/src/i18n/` (frontend), UTF-8, with the Noto Sans Bengali font.

## Parallel work (multiple agents)
The streams in `docs/IMPLEMENTATION_PLAN.md` §0 (A Data/ML, B Engine/Sim, C API/XAI, D Frontend) are designed to run in parallel against the Phase 1 contracts. An agent assigned to one stream should touch only that stream's directories, plus the checkbox lines in the plan.
