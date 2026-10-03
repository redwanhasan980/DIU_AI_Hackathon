# FloatWise — Implementation Plan & Checklist

This plan turns [`SRS.md`](SRS.md) into ordered, checkable tasks.

**Before you start:**
- Read [`../RULES.md`](../RULES.md).
- Tick boxes (`[x]`) in this file as tasks are completed, in the same commit as the work.

**Assumptions to adjust when the event details are known:**
- **About 24 hours** of build time.
- A team of **3–4 people**, each driving AI coding agents.

Hours below are relative to the start of the hackathon (`H+0`). For a 36–48 h event, keep the order and stretch the times. For a shorter event, cut to the **MVP cutline**.

**Legend:**
- **[P0]**: MVP, must ship.
- **[P1]**: should ship.
- **[P2]**: stretch.
- 🔀 marks tasks that can run in parallel with the previous block.

---

## 0. Workstreams & Owners

| Stream | Scope | Owner (fill in) |
|---|---|---|
| **A: Data & ML** | Calendar, generator, features, models, evaluation | ______ |
| **B: Engine & Simulation** | Risk, recommendation, DSO allocation, backtest, impact numbers | ______ |
| **C: API & Explainability** | FastAPI, SHAP service, LLM narrative, cache | ______ |
| **D: Frontend** | React dashboard, all screens | ______ |
| **E: Pitch & QA** (shared) | Deck, demo script, video, README, final checks | ______ |

**Interface contracts are agreed in Phase 1.** After that, streams work independently against them:
- The parquet/CSV schemas in SRS §5.1.
- The API response shapes in SRS §8.
- `backend/floatwise/schemas.py` (pydantic).

D starts with **mock JSON fixtures** that match the schemas, so it never waits on C.

---

## Timeline Overview (24 h)

| Hours | A: Data & ML | B: Engine & Sim | C: API & XAI | D: Frontend | E |
|---|---|---|---|---|---|
| 0–2 | Phase 1 scaffold (all together) | | | | Rules check |
| 2–6 | Phase 2: generator | Phase 5 skeleton on generator output | Phase 8 API skeleton + fixtures | Phase 9 shell + map on fixtures | Deck outline |
| 6–10 | Phase 3–4: baselines, features, models | Phase 5 engine | Phase 7 SHAP + templates | Agent detail | |
| 10–14 | Phase 4 eval + tuning | Phase 6 backtest | Phase 8 real endpoints | DSO plan, Impact | |
| 14–18 | Phase 10 fairness | Impact numbers frozen | LLM narrative + cache | Wire to real API | Deck with real numbers |
| 18–21 | **Feature freeze at H+18**: bug fixes, polish, Phase 11 | | | | Demo video |
| 21–24 | Rehearse ×3, submit | | | | |

> **MVP cutline (must exist by H+16):** data → LightGBM quantiles → recommendation → DSO plan → cached backtest → Map + Agent Detail + Impact screens, with template narratives. Everything else is a bonus.

---

## Phase 0 — Before the Event

- [ ] Confirm hackathon rules: duration, team size, whether pre-written code is allowed (if not, only docs and env setup happen before H+0), submission format (repo, video, slides), and pitch length
- [ ] Assign owners in §0
- [ ] Every laptop: Python 3.11+, Node 20+, git, an editor and the Claude Code CLI working
- [ ] LLM API key obtained and tested (stored in `.env`, **never committed**)
- [ ] Everyone has read `SRS.md`, `CLAUDE.md` and `RULES.md`
- [ ] Verify the Eid dates in SRS Appendix B (Bangladesh observance)
- [ ] Prepare a backup plan: phone hotspot, offline demo, pre-recorded video slot

## Phase 1 — Scaffold & Contracts (H+0 → H+2) [P0]

- [x] Create the repo layout from `CLAUDE.md` (`backend/`, `frontend/`, `data/`, `artifacts/`, `docs/`)
- [x] `backend/pyproject.toml` with pinned deps: pandas, numpy, pyarrow, lightgbm, shap, scikit-learn, fastapi, uvicorn, pydantic, pyyaml, anthropic, pytest, ruff (pulp optional)
- [x] `backend/floatwise/config.py` + `config.yaml`: seed, date ranges, split dates, demo date, archetype parameters, Eid dates, policy defaults (s, θ, α, buffers, K, M), business assumptions
- [x] `backend/floatwise/schemas.py`: pydantic models for Agent, ForecastPoint, Recommendation, Explanation, DsoPlan, SimulationResult, Decision
- [x] `frontend/` Vite + React + TS + Tailwind; `src/api/types.ts` mirrors the schemas; `src/fixtures/*.json` mock responses
- [x] Root `Makefile` targets: `setup`, `data`, `train`, `evaluate`, `simulate`, `narratives`, `api`, `web`, `test`, `lint`, `demo`, `all`
- [x] `.env.example` with `ANTHROPIC_API_KEY=` and `LLM_MODEL=`
- [x] `make test` runs (even with zero tests) and `make lint` passes
- [x] **DoD:** everyone can run `make setup && make test`, and the frontend shows a placeholder page (verified on a fresh clone)

## Phase 2 — Synthetic Data (H+2 → H+6) [P0] · Stream A

- [x] `data/calendar_bd.py`: build the calendar 2024-01-01 → 2026-06-30 with all SRS §5.1 columns (FR-DATA-2)
- [x] `data/agents.py`: 500 agents, 5 archetypes, real district names, jittered lat/lon, DSO/distributor assignment, float capacity (FR-DATA-1)
- [x] `data/demand.py`: true CO/CI demand by the multiplicative model in SRS §5.3 (FR-DATA-3)
  - [x] Weekday/Friday profile per archetype
  - [x] Salary window (garment_belt strong, others mild)
  - [x] Eid curves: rural CO spike, urban CI spike, garment bonus, post-Eid dip
  - [x] Ramadan and Boishakh multipliers
  - [x] Trend + log-normal noise
- [x] `data/shocks.py`: flood/outage/hartal events by district, with a log in `shocks.csv` (FR-DATA-5) [P1]
- [x] `data/simulate_status_quo.py`: day-by-day balances under the status-quo policy → served/unserved, stockout flags, rebalances (FR-DATA-4)
- [x] `data/generate.py` CLI: writes `data/generated/{agents.csv, calendar.csv, daily.parquet, shocks.csv}`, deterministic by seed (FR-DATA-6)
- [x] Data quality checks from SRS §5.4 as `tests/test_data_quality.py`
- [x] `scripts/plot_data_checks.py`: Eid spike, salary window and archetype comparison PNGs in `artifacts/plots/` (FR-DATA-7) [P1]
- [x] `docs/DATA_ASSUMPTIONS.md`: every parameter and why (R-DATA-3)
- [x] Commit the small sample `data/sample/` (50 agents, ≤ 5 MB) for tests (FR-DATA-8) [P1]
- [x] **DoD:** `make data` < 3 min; quality tests pass; the plots visibly show the injected patterns (≈2 s; see README)

## Phase 3 — Baselines & Features (H+6 → H+8) [P0] · Stream A

- [x] `features/build.py`: origin/horizon panel (t, h=1..7) with the SRS §6.2 features
- [x] **Leakage test** `tests/test_no_leakage.py`: corrupt all data after t and assert features at origin t are unchanged (R-ML-2)
- [x] `models/baselines.py`: seasonal-naive and trailing-7-day mean
- [x] Time split per SRS §5.2 in a single function `split_by_date()`; the test period is used only in Phase 4 final eval (R-ML-1)
- [x] **DoD:** feature panel built for train/val; baseline metrics on validation printed

## Phase 4 — Forecast Models (H+8 → H+13) [P0] · Stream A

- [x] `models/train.py`: LightGBM quantile models for {cashout, cashin, net_outflow} × {0.1, 0.5, 0.9} (FR-FCST-2)
- [x] Non-crossing fix after predict (FR-FCST-4)
- [x] Light tuning on validation only (≤ 20 trials)
- [x] `models/evaluate.py`: WAPE, MAE, pinball, coverage; overall / event days / archetype / horizon; vs baselines → `artifacts/metrics.json` (FR-FCST-5)
- [x] Censoring handling: stockout-day feature or exclusion; evaluate against true demand (FR-FCST-6) [P1]
- [x] `models/predict.py`: precompute forecasts for every agent and origin in the test period → `artifacts/forecasts.parquet` (fast API reads)
- [x] Auto-generate `artifacts/model_card.md`
- [x] Final test-set evaluation run **once**; numbers recorded
- [x] **DoD:** acceptance table in SRS §6.4 filled with real numbers (honest even if a target is missed)

## Phase 5 — Decision Engine (H+4 → H+12, 🔀 starts on generator output) [P0] · Stream B

- [x] `engine/risk.py`: quantile interpolation → `p_cash_stockout`, `p_efloat_stockout` (SRS §7.1)
- [x] `engine/recommend.py`: action, amount (ceil to ৳1,000), reason codes, 7-day outlook (SRS §7.2, FR-REC-1..5)
- [x] `engine/allocate.py`: greedy DSO plan with K and M constraints + excluded list (SRS §7.3)
- [x] Unit tests: low balance before Eid → TOP_UP_CASH; high balance → NO_ACTION; capacity exceeded → NEEDS_EXTRA_FLOAT; plan never exceeds K or M; amounts are deterministic
- [x] Exact (knapsack DP) allocation vs greedy comparison (FR-ALLOC-4) [P2]
- [x] **DoD:** `pytest tests/test_engine.py` green; the engine works on mocked quantiles before the real models exist

## Phase 6 — Impact Simulator (H+10 → H+16) [P0] · Stream B

- [x] `simulation/backtest.py`: replay the test period on **true demand** under status quo vs FloatWise (rebalance lead time 1 day, DSO capacity respected) (FR-SIM-1)
- [x] Metrics: stockout agent-days, failed CO/CI count and ৳, lost commission, average idle cash, trips (FR-SIM-2)
- [x] Eid-2026 daily timeline series for the chart
- [x] Service-level sweep (0.80 → 0.99) → trade-off curve data (FR-SIM-3) [P1]
- [x] Per-1,000-agents-per-month extrapolation using config assumptions (FR-SIM-5) [P1]
- [x] Cache the default scenario in `artifacts/simulation_default.json` (FR-SIM-4)
- [x] **DoD:** KPI table in SRS §12 filled with real numbers; idle cash not above status quo (if it is, tune s/buffer on **validation**, not test). ⚠ Idle cash is +2.3 %: tuned on validation with a ≤ +5 % cap, reported as missed in SRS §12

## Phase 7 — Explainability & LLM Narrative (H+6 → H+18) [P0] · Stream C

- [x] `explain/shap_explain.py`: top-5 SHAP drivers for P50 cash-out at h=1, with a human-readable label map (en + bn) (FR-XAI-1)
- [x] `explain/templates.py`: deterministic bn/en narrative from reason codes + numbers (FR-XAI-4). **Build this before the LLM.**
- [x] `explain/llm.py`: Anthropic client, model from env `LLM_MODEL`; system prompt says to use only the given JSON, ≤ 3 sentences, no new numbers (FR-XAI-2)
- [x] Numeric post-check: every number in the output must exist in the input, else use the template (FR-XAI-3) [P1]
- [x] `scripts/build_narratives.py`: pre-generate bn + en for demo agents and the demo date → `artifacts/narratives_cache.json` (FR-XAI-5)
- [x] Tests: the template always works without a key; the post-check rejects an injected fake amount
- [x] **DoD:** explanation endpoint returns `source: cache|llm|template` and never errors

## Phase 8 — API (H+2 → H+16, 🔀) [P0] · Stream C

- [x] `api/main.py` FastAPI app, CORS limited to the frontend origin, error format per SRS §8
- [x] Endpoints serve **fixtures first** (H+4), then real artifacts as they land
- [x] `/health`, `/agents`, `/agents/{id}`, `/agents/{id}/forecast`, `/agents/{id}/recommendation`, `/agents/{id}/explanation`
- [x] `/dso/{id}/plan`, `/network/summary`, `/simulate` (cached default + live recompute if fast), `/metrics/model`
- [x] `/decisions` POST/GET with JSON-file storage (FR-HITL-1)
- [x] `/calendar` [P1]
- [x] API tests with FastAPI TestClient against `data/sample/`
- [x] **DoD:** `/docs` lists all endpoints; every GET < 300 ms on the demo date (measured 2–101 ms after startup warm-up)

## Phase 9 — Frontend (H+2 → H+18, 🔀) [P0] · Stream D

- [x] App shell: nav, date picker (default 2026-03-15), language toggle, event banner
- [x] `lib/format.ts`: `৳1,20,000` lakh formatting, Bangla digits for the agent card
- [x] **Screen 1 Network Map** (react-leaflet): risk-coloured markers + KPI tiles [P0]
- [x] **Screen 2 Risk List**: sortable/filterable table [P0]
- [x] **Screen 3 Agent Detail**: forecast band chart, balance vs need, recommendation card with Approve/Modify/Reject, SHAP bars, AI explanation labelled "AI-generated" [P0]
- [x] **Screen 4 DSO Plan**: ordered list, cash-to-carry, capacity meter, excluded list [P0]
- [x] **Screen 5 Impact Simulator**: side-by-side KPIs + Eid timeline (static from cache) [P0]; service-level slider + trade-off curve [P1]
- [x] **Screen 6 Model & Fairness**: metrics and per-archetype table [P1]
- [x] **Screen 7 Agent Mobile Card**: Bangla, big text, one action [P1]
- [x] Switch from fixtures to the real API via `VITE_API_URL`
- [x] Loading/error states; works at 360 px; colour + label for risk (not colour only)
- [x] **DoD:** the demo script (SRS §14) can be clicked through without errors (`make e2e`: 21/21 pass)

## Phase 10 — Responsible AI, Security & Fairness (H+14 → H+18) [P0/P1]

- [x] Fairness table: WAPE and stockout reduction per archetype and rural vs urban → `artifacts/fairness.json` + UI [P1]
- [x] Confirm no PII fields exist; shop names are synthetic [P0]
- [x] `.env` is git-ignored; secret scan of the repo (`git grep -i "sk-ant"` returns nothing) [P0]
- [x] The LLM receives only structured JSON; no user free text reaches the prompt [P0]
- [x] Every action requires human approval in the UI; `NEEDS_EXTRA_FLOAT` shown as escalation [P0]
- [x] Assumptions list visible in the UI (business values labelled "assumption") [P1]

## Phase 11 — Demo Hardening & Submission (H+18 → H+24) [P0] · Stream E + all

- [ ] **Feature freeze at H+18**: only bug fixes after this
- [x] `make demo` starts API + web with cached artifacts and **works with Wi-Fi off**
- [x] Numbers in the deck = UI = `artifacts/*.json` (single source)
- [x] README: problem, solution, screenshots, architecture diagram, how to run, results table, Responsible AI, limitations, next steps
- [ ] Pitch deck (≈ 8–10 slides): Problem → Who → Why AI → Demo → Results → Responsible AI → Scale path → Team
  - Draft: 16 animated slides, numbers from `artifacts/*.json`, at https://claude.ai/artifact/KiGmc8LGx4vfnn1svfmMm2 (private until shared). Still to do: add a Team slide and share the link.
- [ ] Demo video (2–3 min) recorded as a backup
- [ ] Rehearse the demo ×3 with a timer; prepare answers for likely judge questions (see below)
- [x] Fresh clone → `make setup all demo` works on a second laptop
- [ ] Submit the repo link, video and deck before the deadline (aim for 1 h early)

---

## Likely Judge Questions (prepare answers)

1. *Why not just use last year's numbers?* Eid moves about 11 days each year, and salary windows and remittance overlap differently each year. Show the baseline vs model error on event days.
2. *Your data is synthetic; how do we know it works?* We use a time-based held-out test, injected ground truth and documented assumptions. Then a shadow-mode pilot on aggregated, anonymised agent ledgers (no customer data needed).
3. *What if the model is wrong?* Quantiles plus a service level, a human approves, and the policy degrades gracefully to the status-quo rule.
4. *Isn't more cash just more idle money?* Show the idle-cash KPI and the service-level trade-off curve.
5. *Where exactly is the AI vs rules?* ML forecasts and SHAP; the deterministic engine converts them to actions; the LLM only explains.
6. *Fairness?* Show the per-archetype and rural-vs-urban table.

## Risk Fallbacks (decide fast, don't debate)

| If… | Then… |
|---|---|
| LightGBM quantiles misbehave by H+12 | Ship P50 model + empirical residual quantiles from validation |
| Map library fights you > 30 min | Replace with a district-grouped table plus a bar chart |
| LLM API unavailable | Templates + cached narratives (already P0) |
| Backtest too slow | Run on a 100-agent subset; state it clearly |
| Behind schedule at H+16 | Drop all P1/P2, polish the MVP path only |
