# FloatWise — Software Requirements Specification (SRS)

**AI Agent Liquidity Forecaster for upay**
AI Hackathon 2026 · DIU CPC × upay · Track 05: Merchant & Agent Intelligence

| Field | Value |
|---|---|
| Version | 1.0 |
| Status | Baseline for implementation |
| Related docs | [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md), [`../CLAUDE.md`](../CLAUDE.md), [`../RULES.md`](../RULES.md) |

Requirement priorities:
- **P0**: must have for the demo (MVP).
- **P1**: should have. Strongly improves the score.
- **P2**: stretch goal.

---

## 1. Introduction

### 1.1 Purpose
This document specifies what FloatWise must do, end to end: synthetic data, ML forecasting, decision engine, explanation layer, API, dashboard and impact simulation. It is the single source of truth for the team and for the AI coding agents that build the system.

### 1.2 Problem in one paragraph
Mobile financial service (MFS) agents in Bangladesh hold two balances:
- **Physical cash**, used to pay out cash-outs.
- **E-money (e-float)**, used to accept cash-ins.

Demand on these balances swings hard around:
- Eid-ul-Fitr and Eid-ul-Adha.
- Garment salary days (roughly the 1st–10th of each month).
- Pre-Eid remittance inflows, Ramadan and local events.

When an agent runs out of cash, the customer hears "cash nai, pore ashen" ("no cash, come back later"). The transaction fails, the agent and upay lose commission, and the customer may move to a competitor. Agents and distributor field officers (DSOs) rebalance today by intuition, using recent averages. Those lag behind sudden spikes.

Eid also moves about 11 days earlier every Gregorian year. That means "same month last year" rules of thumb break.

### 1.3 Problem statement (hackathon template)
> **For** upay agents and the distributor field officers (DSOs) who rebalance them, **unpredictable cash and e-float shortages around Eid, salary days and remittance peaks cause** failed cash-out/cash-in transactions, lost commission and customer churn to competitors. **We will build** FloatWise, an AI liquidity forecaster that **uses** synthetic agent transaction history, a Bangladesh event calendar and area profiles **to** predict each agent's 1–7-day cash and e-float needs and recommend prioritised, human-approved rebalancing. **Success is measured by** fewer stockout days and less failed-transaction value than the current reactive approach, at equal or lower idle cash.

### 1.4 Scope
**In scope:**
- A synthetic but realistic agent network.
- Probabilistic demand forecasts.
- Stockout risk scoring.
- Rebalancing recommendations.
- A capacity-constrained DSO visit plan.
- A backtest simulator that shows business impact.
- SHAP-based reasons plus an LLM-written Bangla/English explanation.
- A REST API and a web dashboard.

**Out of scope:** see §16.

### 1.5 Definitions

| Term | Meaning |
|---|---|
| Agent | A retail point (shop) that performs cash-in and cash-out for MFS customers |
| Cash-in (CI) | Customer gives cash to the agent → agent cash ↑, agent e-float ↓ |
| Cash-out (CO) | Agent gives cash to the customer → agent cash ↓, agent e-float ↑ |
| E-float | The agent's e-money balance in the MFS system |
| Float | Total working capital = cash + e-float |
| Stockout | The agent cannot serve a transaction because cash (for CO) or e-float (for CI) is insufficient |
| Rebalancing | Converting between cash and e-float through the distributor/DSO or a bank |
| DSO | Distributor Sales Officer, the field staff who visit and rebalance agents |
| Service level (s) | Target probability of **not** stocking out on a day (default 0.99, tuned on validation) |
| WAPE | Weighted absolute percentage error = Σ\|y−ŷ\| / Σy |
| Pinball loss | The loss function used to evaluate quantile forecasts |
| Origin date (t) | The date on which a forecast is made; only data ≤ t may be used |
| Horizon (h) | Days ahead of the origin, h ∈ {1..7} |

### 1.6 References
- AI Hackathon 2026 Student Project Guideline & Innovation Playbook (DIU CPC × upay). Covers the tracks, the 9-step logic chain, data policy, Responsible AI rules and the evaluation framework.

---

## 2. Overall Description

### 2.1 Product perspective
FloatWise is a standalone prototype. It is designed so its API could later sit next to a real MFS core: agent ledger in, recommendations out to a DSO app or agent app. Data preparation, ML inference, business rules and the LLM narrative are separate layers. This follows the guideline's architecture expectations.

```
Synthetic data ─▶ Feature layer ─▶ ML engine (quantile forecasts)
                                        │
                                        ▼
                   Decision engine (risk, top-up, DSO allocation)  ◀── business rules / config
                                        │
                  ┌─────────────────────┼──────────────────────┐
                  ▼                     ▼                      ▼
          SHAP reasons ─▶ LLM narrative (bn/en)        Backtest simulator
                  │                     │                      │
                  └──────────▶  FastAPI  ◀─────────────────────┘
                                        │
                                        ▼
                     React dashboard (DSO / Area manager / Agent view)
                                        │
                                        ▼
                     Human approves action ─▶ outcome logged ─▶ feedback loop
```

### 2.2 Users and personas

| Persona | Goal | Key screens |
|---|---|---|
| **Rahim, DSO (Gazipur)**: visits 8–12 agents/day with a cash bag | Know which agents to visit first and how much to carry | DSO Plan, Agent Detail |
| **Nasrin, Area Manager (Dhaka North)**: oversees 5 DSOs | See risk across the area before Eid; approve plans | Network Map, Risk List |
| **Karim, Agent (rural Sylhet)**: runs a shop, low digital literacy | A simple Bangla message: how much cash to keep tomorrow | Agent Card (Bangla, large text) |
| **upay Ops/Strategy team** | Prove business value; tune service level vs idle cash | Impact Simulator, Model Report |

### 2.3 Product functions (summary)
1. Generate a synthetic agent network and 30 months of daily transactions with documented, injected patterns.
2. Forecast daily cash-out, cash-in and net cash outflow for each agent, 1–7 days ahead, as quantiles (P10/P50/P90 etc.).
3. Convert forecasts plus current balances into stockout risk and a recommended action (top up cash / top up e-float / no action).
4. Build a daily DSO visit plan under visit and cash-carry capacity limits.
5. Explain every recommendation: top drivers (SHAP), plus a plain Bangla/English narrative grounded only in structured data.
6. Backtest FloatWise against the status-quo policy and report stockouts, failed value, idle cash and trips.
7. Serve all of this through a REST API and a web dashboard, with a human-approval step.

### 2.4 Operating environment
- Python 3.11+.
- Node 20+.
- Runs locally on a laptop (no GPU needed).
- Modern Chrome/Firefox, desktop and mobile widths.
- An LLM API key is optional. Without one, the system uses deterministic templates.

### 2.5 Constraints
- **C1:** No production or real customer data. Synthetic, public or self-generated data only.
- **C2:** The system must never move money or take financial decisions on its own. A human approves every action.
- **C3:** Money amounts and decisions come from deterministic code and ML. **Never from the LLM.**
- **C4:** Hackathon time budget (assumed about 24 h; see the implementation plan).
- **C5:** The demo must work offline (cached LLM outputs, local data, no external calls required).

### 2.6 Assumptions and dependencies
- **A1:** Agent behaviour is modelled at **daily** granularity. Intraday timing is approximated with an overlap factor α (§7.2).
- **A2:** An agent can be rebalanced at most once per day. Lead time is 1 day: a recommendation made on day t takes effect at the opening of day t+1.
- **A3:** Eid dates follow the Bangladesh observance. They are approximations, stored in config and easy to correct.
- **A4:** Fees and commissions are configurable assumptions, not official upay tariffs.
- **A5:** All synthetic assumptions are recorded in `docs/DATA_ASSUMPTIONS.md` (rule R-DATA-3).

---

## 3. Idea Logic Chain (guideline §10)

| Step | Answer |
|---|---|
| 1. User | upay agents, DSOs, area managers |
| 2. Problem | Cash/e-float stockouts at predictable-but-shifting peaks → failed transactions, lost commission, churn, emergency DSO trips |
| 3. Why now | Agent transaction history is rich time-series data. Event-driven demand (moving Eid, salary windows) is exactly what ML forecasting handles and averages miss |
| 4. Solution | Forecast → risk → recommendation → DSO plan → human approval, with explanations |
| 5. AI role | **Prediction** (quantile LightGBM), **optimization** (capacity-constrained allocation), **generation** (grounded Bangla narrative), **explanation** (SHAP) |
| 6. Impact | Target: ≥40 % fewer stockout days and ≥40 % less failed-transaction value vs status quo, with idle cash not higher (§12) |
| 7. Data | Synthetic network: 500 agents × ~900 days, with injected Eid/salary/remittance/Ramadan/shock patterns |
| 8. Validation | Time-based train/val/test split; WAPE and pinball loss vs baselines; policy backtest over Eid 2026; per-segment fairness check |
| 9. Scale | Same API on governed, anonymised upay agent ledgers → shadow mode → pilot with one distributor → rollout (§13) |

---

## 4. Functional Requirements

### 4.1 Synthetic data (FR-DATA)

| ID | Requirement | Pri |
|---|---|---|
| FR-DATA-1 | Generate `agents` with id, synthetic shop name, archetype, division/district/upazila, lat/lon, `dso_id`, `distributor_id`, total float capacity, opening cash and e-float | P0 |
| FR-DATA-2 | Generate a Bangladesh `calendar` (2024-01-01 → 2026-06-30): weekday, Friday/Saturday weekend, Eid-ul-Fitr, Eid-ul-Adha, days-to/after each Eid, Ramadan, salary window, Pohela Boishakh, other public holidays | P0 |
| FR-DATA-3 | Generate **true daily demand** (CO and CI amount and count) per agent from archetype base level × calendar multipliers × trend × noise (§5.3) | P0 |
| FR-DATA-4 | Simulate balances day by day under the **status-quo policy**: served vs unserved demand, stockout flags, rebalance amounts. Observed data = served amounts (censored), as in reality | P0 |
| FR-DATA-5 | Inject random shocks (local flood, network outage, hartal) as a ground-truth event log, so anomalies are known | P1 |
| FR-DATA-6 | A deterministic seed gives byte-identical outputs | P0 |
| FR-DATA-7 | Validation notebook/script plots showing that injected patterns exist (Eid spike, salary window, archetype differences) | P1 |
| FR-DATA-8 | Small committed sample (≤ 5 MB) for CI/tests. The full dataset is regenerated by `make data` | P1 |

### 4.2 Forecasting (FR-FCST)

| ID | Requirement | Pri |
|---|---|---|
| FR-FCST-1 | Baselines: seasonal-naive (same weekday last week) and trailing-7-day mean | P0 |
| FR-FCST-2 | Global LightGBM quantile models for `cashout_amt` and `cashin_amt` at quantiles {0.1, 0.5, 0.9}, horizon h ∈ 1..7 as a feature (direct multi-horizon). Net flow is derived by the engine (§7), not modelled separately | P0 |
| FR-FCST-3 | Features use only information known at origin t (lags/rolling stats ≤ t) plus calendar features of the target date (known in advance) | P0 |
| FR-FCST-4 | Enforce non-crossing quantiles (sort or clip after prediction) | P0 |
| FR-FCST-5 | Evaluation report: WAPE, MAE, pinball loss, P10–P90 coverage. Overall, on **event days** (±7 days of Eid, salary window), per archetype, per horizon, vs baselines. Saved to `artifacts/metrics.json` | P0 |
| FR-FCST-6 | Censoring handling: compare keep / exclude / inflate on a held-out Eid (`scripts/censoring_experiment.py`); the selected mode (`inflate`) lifts stockout-day labels to the P75 ratio of uncensored peers. Evaluate against true demand | P1 |
| FR-FCST-7 | Cold-start: forecast for agents with < 28 days of history using archetype/area priors | P2 |

### 4.3 Risk and recommendation (FR-REC)

| ID | Requirement | Pri |
|---|---|---|
| FR-REC-1 | For each agent and day, compute `p_cash_stockout` and `p_efloat_stockout` from the quantile forecasts and current balances (§7.1) | P0 |
| FR-REC-2 | Recommend an action: `TOP_UP_CASH`, `TOP_UP_EFLOAT`, `NO_ACTION` or `NEEDS_EXTRA_FLOAT` (total float insufficient → escalate to a human), with amount rounded to ৳1,000 (§7.2) | P0 |
| FR-REC-3 | Each recommendation carries machine-readable **reason codes** (e.g. `EID_FITR_IN_5_DAYS`, `SALARY_WINDOW`, `BALANCE_BELOW_P90`) | P0 |
| FR-REC-4 | Configurable service level s ∈ [0.80, 0.99] and minimum buffer. Defaults are chosen on the validation period by `scripts/tune_policy.py` (currently s = 0.99, θ = 0.10) | P0 |
| FR-REC-5 | 7-day outlook: flag the first day in the horizon where risk exceeds the threshold ("pre-position by Wednesday") | P1 |

### 4.4 DSO allocation (FR-ALLOC)

| ID | Requirement | Pri |
|---|---|---|
| FR-ALLOC-1 | For a DSO and date, produce an ordered visit list under constraints: max visits K (default 10) and max cash carried M (default ৳10,00,000) | P0 |
| FR-ALLOC-2 | Priority = expected failed value prevented = p_stockout × expected shortfall (৳). Greedy by priority, respecting capacity (§7.3) | P0 |
| FR-ALLOC-3 | Agents left out are listed with the reason "capacity" and the advice "self-rebalance at distributor point" | P1 |
| FR-ALLOC-4 | Optimal allocation via ILP (PuLP), compared with greedy | P2 |

### 4.5 Impact simulator (FR-SIM)

| ID | Requirement | Pri |
|---|---|---|
| FR-SIM-1 | Replay the **test period** day by day under two policies on the same true demand: (a) status quo, (b) FloatWise. Under FloatWise, DSO-visited agents execute the recommendation; unvisited agents get it in the app and a configurable share (`self_rebalance_compliance`, default 70 %) self-rebalance as advised, the rest keep their own rule | P0 |
| FR-SIM-2 | Report per policy: stockout agent-days, failed CO/CI count and ৳ value, lost commission ৳, average idle cash ৳, rebalancing trips | P0 |
| FR-SIM-3 | Parameters: service level, buffer, DSO capacity, date range, area filter. The UI shows the trade-off curve of stockouts vs idle cash across service levels | P1 |
| FR-SIM-4 | Results are cached for the default scenario so the demo loads instantly | P0 |
| FR-SIM-5 | Extrapolate impact to "per 1,000 agents per month" using documented assumptions | P1 |

### 4.6 Explainability and narrative (FR-XAI)

| ID | Requirement | Pri |
|---|---|---|
| FR-XAI-1 | SHAP top-5 feature contributions for an agent's forecast (P50 cash-out, horizon 1), mapped to human-readable labels | P0 |
| FR-XAI-2 | A narrative generator takes a structured JSON (forecast, balances, recommendation, reason codes, SHAP drivers) and returns a short explanation in **Bangla** or **English** | P0 |
| FR-XAI-3 | The LLM must not introduce numbers absent from the input JSON. Numeric post-check: any ৳ figure in the output must match an input value, else fall back to the template | P1 |
| FR-XAI-4 | Deterministic template fallback (bn/en) when no API key is set, the API is down or validation fails | P0 |
| FR-XAI-5 | Pre-generated narratives are cached for the demo agents (offline demo) | P0 |
| FR-XAI-6 | The UI visually separates **prediction** (numbers), **assumption** (config) and **generated text** (labelled "AI-generated explanation") | P0 |

### 4.7 API (FR-API)
See §8. **P0:** all endpoints marked P0 there. OpenAPI docs at `/docs`.

### 4.8 User interface (FR-UI)
See §9.

### 4.9 Human-in-the-loop and feedback (FR-HITL)

| ID | Requirement | Pri |
|---|---|---|
| FR-HITL-1 | Every recommendation has Approve / Modify amount / Reject buttons. The decision and a reason are stored (`decisions` table/JSON) | P0 |
| FR-HITL-2 | No recommendation is "executed". Approval only records intent (prototype) | P0 |
| FR-HITL-3 | Decisions log viewable. Rejection reasons are summarised as a feedback signal for retraining (described; actual retraining is P2) | P1 |

---

## 5. Data Requirements

### 5.1 Entities and schemas

**`agents.csv`**

| Column | Type | Notes |
|---|---|---|
| agent_id | str | `AG00001` … |
| shop_name | str | Synthetic, e.g. "Mayer Doa Telecom". No real names |
| archetype | enum | `urban_residential`, `garment_belt`, `rural_remittance`, `market_hub`, `university_area` |
| division, district, upazila | str | Real geography names only (no personal data) |
| lat, lon | float | Jittered points inside the district |
| dso_id, distributor_id | str | ~25 agents per DSO (same district); ~5 DSOs per distributor |
| float_capacity | int ৳ | Total cash + e-float the agent can hold |
| onboard_date | date | |

**`calendar.csv`**: one row per date. Columns: `date, dow, is_friday, is_saturday, is_eid_fitr, is_eid_adha, days_to_eid_fitr, days_to_eid_adha, days_after_eid, is_ramadan, is_salary_window, salary_day_index, is_boishakh, is_public_holiday, event_name`.

**`daily.parquet`**: one row per (agent_id, date).

| Column | Notes |
|---|---|
| cashout_demand_amt, cashin_demand_amt | **Ground truth** (hidden from the model; used for evaluation and simulation) |
| cashout_amt, cashin_amt | Served (observed) amounts |
| cashout_cnt, cashin_cnt | Served counts |
| unserved_cashout_amt, unserved_cashin_amt | Failed demand |
| open_cash, open_efloat, close_cash, close_efloat | Balances |
| stockout_cash, stockout_efloat | bool |
| rebalance_cash_amt | + cash delivered / − cash collected |
| shock_flag | Injected shock active |

**`shocks.csv`**: `shock_id, type, district, start_date, end_date, multiplier`.

### 5.2 Scale and split
- 500 agents (P0; configurable). Dates 2024-01-01 → 2026-06-30 (~912 days, ~456k rows).
- **Time-based split, never random:**
  - Train: 2024-01-01 → 2025-06-30 (contains Eid-ul-Fitr and Eid-ul-Adha of both 2024 and 2025).
  - Validation: 2025-07-01 → 2025-12-31.
  - **Test (untouched until final eval):** 2026-01-01 → 2026-06-30 (contains Eid-ul-Fitr ≈ 2026-03-20 and Eid-ul-Adha ≈ 2026-05-27).
- **Demo "today":** `2026-03-15`, about 5 days before Eid-ul-Fitr 2026.

### 5.3 Generation model (true demand)
```
demand_CO(agent, d) = base_CO[archetype] × size_factor[agent]
                      × dow_mult[archetype][dow]
                      × salary_mult[archetype](salary_day_index)
                      × eid_mult[archetype](days_to_eid, days_after_eid)
                      × ramadan_mult × boishakh_mult × shock_mult(district, d)
                      × trend(d) × noise  (noise ~ LogNormal(0, σ_archetype))
```
CI demand follows the same pattern with its own multipliers. Initial values (all in config, all documented):

| Archetype | Base CO/day | Base CI/day | Signature pattern |
|---|---|---|---|
| urban_residential | ৳1,50,000 | ৳1,80,000 | **CI spike before Eid** (people send money home) → e-float stockouts |
| garment_belt | ৳2,50,000 | ৳1,00,000 | **CO spike on salary days 1–10** and the pre-Eid bonus |
| rural_remittance | ৳80,000 | ৳40,000 | **CO spike before Eid** (×2–3) as remittance arrives |
| market_hub | ৳3,00,000 | ৳3,00,000 | High volume both ways; Boishakh and pre-Eid shopping |
| university_area | ৳60,000 | ৳50,000 | Month-start CI from families; drops in vacations |

Other rules:
- Ticket size ~ LogNormal, mean ৳1,500–৳3,000 by archetype. Count = amount / ticket.
- Status-quo policy (used to create observed data and as the comparison baseline):
  - Each morning, if `open_cash < 0.3 × mean_CO_7d`, the agent rebalances to `target_cash = 1.0 × mean_CO_7d`, capped by float capacity.
  - The same logic applies to e-float with CI.
  - Rebalancing takes effect at the next day's opening (lead time 1).

### 5.4 Data quality checks (P0)
- No negative balances.
- served ≤ demand.
- Cash + e-float conservation (except rebalancing with the distributor).
- Every date in the calendar.
- Each archetype is ≥ 10 % of agents.
- The Eid spike is visible: mean CO in the 7 days before Eid ≥ 1.5× baseline for `rural_remittance`.

---

## 6. ML Specification

### 6.1 Targets
`cashout_amt` and `cashin_amt`, each at quantiles q ∈ {0.1, 0.5, 0.9}, expressed as a ratio to the agent's trailing 28-day mean (so one global model learns multipliers across agents of different size).

### 6.2 Features (computed at origin t for target date t+h)

| Group | Features |
|---|---|
| Horizon | `h` |
| Target-date calendar | dow, is_friday, days_to_eid_fitr/adha (clipped to ±30), days_after_eid, is_ramadan, salary_day_index, is_salary_window, is_boishakh, is_holiday |
| Lags (≤ t) | y_t, y_{t-1}, y_{t-6} (same weekday next), y_{t-13}, rolling mean/std 7/14/28, rolling max 28 |
| Event memory | Agent's mean multiplier around the **previous** Eid (if available ≤ t) |
| Agent static | archetype, float_capacity, district (categorical), DSO density |
| Censoring | stockout count in the last 7 days |

Rule: no feature may use data from after t (leakage test required, R-ML-2).

### 6.3 Models
- LightGBM `objective="quantile"`, one model per (target, q).
- Hyperparameters tuned lightly on validation only (≤ 20 Optuna trials or a manual grid).
- Saved to `artifacts/models/`. A `model_card.md` is generated.

### 6.4 Evaluation and acceptance

| Metric | Acceptance (test set) |
|---|---|
| WAPE P50 cash-out vs seasonal-naive | ≥ 20 % relative improvement overall |
| WAPE P50 cash-out on event days | ≥ 35 % relative improvement |
| P10–P90 empirical coverage | 72–88 % (target 80 %) |
| Per-archetype WAPE | No archetype worse than the baseline (fairness) |

If an acceptance target is missed, report the true number honestly (R-ML-5). Never tune on the test set.

---

## 7. Decision Engine Specification (deterministic)

### 7.1 Stockout probability
For the next day (h=1), with predicted CO quantiles Q_CO(q):
- `p_cash_stockout` is estimated by locating `open_cash_eff = open_cash + α × Q_CI(0.5)` within the CO quantile curve (linear interpolation between known quantiles, flat beyond them).
- So if `open_cash_eff` equals Q_CO(0.9), then p ≈ 0.10.
- The e-float case is symmetric: `open_efloat + α × Q_CO(0.5)` against the Q_CI quantiles.
- α (intraday overlap factor, default 0.5) captures that some same-day inflows arrive in time to fund outflows. It is configurable and documented.

### 7.2 Recommendation
```
target_cash(s)   = ceil_1000( Q_CO(s) − α·Q_CI(0.5) + min_buffer_cash )
target_efloat(s) = ceil_1000( Q_CI(s) − α·Q_CO(0.5) + min_buffer_efloat )
risky = p_cash_stockout ≥ θ or p_efloat_stockout ≥ θ        (total float = cash + e-float is fixed)

if target_cash(s) + target_efloat(s) ≤ float_capacity:
    cash risky and below target    → TOP_UP_CASH   to target_cash
    e-float risky and below target → TOP_UP_EFLOAT to target_efloat
elif risky:                          best split: cash = capacity × target_cash / (target_cash + target_efloat)
                                     → TOP_UP_CASH or TOP_UP_EFLOAT by the sign of the change
if risky and target_cash(0.9) + target_efloat(0.9) > float_capacity:
                                     → NEEDS_EXTRA_FLOAT (human escalation; amount = float missing even at
                                       the P90 level; the best split is still applied)
otherwise                            → NO_ACTION
```
Defaults: s = 0.99, θ = 0.10 (chosen on validation by `scripts/tune_policy.py`; s is high because P90 forecasts are slightly over-confident around events), min_buffer = ৳5,000. The CDF built from P10/P50/P90 has explicit tails (§7.1, `engine/risk.py`). Reason codes are attached from the calendar flags (event countdowns from the decision date, day types for the effective date) and the balance state. Risk bands: high ≥ 0.5, medium ≥ θ, else low.

### 7.3 DSO allocation (greedy, P0)
1. Candidates are the agents of the DSO with action ∈ {TOP_UP_CASH, TOP_UP_EFLOAT}.
2. `priority = expected shortfall = E[(demand − available)+]` in taka (cash or e-float side, whichever is larger), computed exactly from the piecewise-linear CDF. This already folds in the stockout probability.
3. Sort by priority, descending. Add agents while visits < K and cumulative cash carried ≤ M.
4. Output the ordered plan plus the excluded list.

### 7.4 Business-value assumptions (config, labelled "assumption" in UI)
- Cash-out fee to customer: 1.85 % of amount.
- Agent + distributor share of that fee: 0.6 %.
- Lost-customer probability after a failed cash-out: 5 %.
- Opportunity cost of idle cash: 10 % annual.

All of these are **illustrative**, not upay tariffs.

---

## 8. API Specification (FastAPI, JSON, prefix `/api/v1`)

| Method | Path | Description | Pri |
|---|---|---|---|
| GET | `/health` | Status, model version, data date range | P0 |
| GET | `/agents` | List; query `district`, `archetype`, `dso_id`, `risk_min`, `date` → id, name, lat/lon, archetype, risk, action | P0 |
| GET | `/agents/{id}` | Profile + balances on `date` + last 28 days history | P0 |
| GET | `/agents/{id}/forecast` | `date`, `horizon≤7` → per day: CO/CI/net quantiles + actuals if available | P0 |
| GET | `/agents/{id}/recommendation` | `date`, `service_level` → action, amount, p_stockout, reason_codes, 7-day outlook | P0 |
| GET | `/agents/{id}/explanation` | `date`, `lang=bn\|en` → shap drivers, narrative, `source: llm\|template\|cache` | P0 |
| GET | `/dso/{dso_id}/plan` | `date`, `max_visits`, `max_cash` → ordered plan + excluded | P0 |
| GET | `/network/summary` | `date` → counts by risk band, by district; total recommended ৳ | P0 |
| POST | `/simulate` | Body: policy params, date range, filters → metrics for status quo vs FloatWise | P0 (cached default) |
| GET | `/metrics/model` | Evaluation report JSON | P0 |
| GET | `/calendar` | Events within a range | P1 |
| POST | `/decisions` | Approve/modify/reject a recommendation | P0 |
| GET | `/decisions` | Decision log | P1 |

Error format: `{"error": {"code": "...", "message": "..."}}`. Validation via pydantic. Response time < 300 ms for GET (precomputed or cached forecasts for the demo date range).

---

## 9. UI Specification (React + Vite + TypeScript + Tailwind + Recharts + react-leaflet)

| Screen | Content | Pri |
|---|---|---|
| **1. Network Map** | Bangladesh map with agent dots coloured by risk band (green/amber/red). Date picker (default 2026-03-15). KPI tiles: agents at risk tomorrow, ৳ recommended, upcoming event banner ("Eid-ul-Fitr in 5 days") | P0 |
| **2. Risk List** | Sortable table: agent, area, archetype, p_stockout, action, amount. Filters | P0 |
| **3. Agent Detail** | Forecast chart (actual history + P10–P90 band + P50 line, 7 days ahead); balances vs needs; recommendation card with Approve/Modify/Reject; SHAP driver bars; AI explanation (bn/en toggle, "AI-generated" label) | P0 |
| **4. DSO Plan** | Ordered visit list with cash to carry, capacity meter, excluded agents, route on map (ordering only) | P0 |
| **5. Impact Simulator** | Status quo vs FloatWise side by side (stockouts, failed ৳, idle cash, trips); service-level slider → trade-off curve; Eid 2026 timeline of daily stockouts | P0 (static cached) / P1 (interactive) |
| **6. Model & Fairness** | Metrics vs baselines, per-archetype and per-horizon error, coverage, assumptions list | P1 |
| **7. Agent Mobile Card** | Large Bangla text: "আগামীকাল কমপক্ষে ৳১,২০,০০০ নগদ রাখুন", reason in one line, icon-based | P1 |

UI rules:
- Money is shown as `৳1,20,000` (Bangladeshi lakh grouping).
- Bangla font: Noto Sans Bengali / Hind Siliguri.
- Readable at 360 px width.
- Colour-blind-safe risk palette with icons/labels, not colour alone.

---

## 10. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | Performance | Full pipeline (`make data train evaluate simulate`) < 15 min on a laptop. API GET < 300 ms |
| NFR-2 | Reliability | Demo runs with **no internet** (cached narratives, local data). `make demo` starts everything |
| NFR-3 | Reproducibility | A single seed in config. Pinned dependencies. `make all` reproduces the metrics |
| NFR-4 | Usability | Bangla-first agent view; English/Bangla toggle elsewhere; ≤ 3 clicks from map to approval |
| NFR-5 | Security | API key from env only; CORS restricted to the frontend origin; input validation; no secrets in git; LLM receives only structured JSON (no free text from users) |
| NFR-6 | Privacy | Synthetic data only; no names or phones of real people; shop names generated |
| NFR-7 | Maintainability | Layered packages (data / features / models / engine / explain / api); type hints; ruff-clean; tests for the engine and leakage |
| NFR-8 | Portability | Optional Docker Compose (P2) |
| NFR-9 | Observability | Structured logs; every recommendation logged with model version, inputs hash, output |

---

## 11. Responsible AI & Security (guideline §14)

| Principle | How FloatWise meets it |
|---|---|
| Privacy | 100 % synthetic data; assumptions documented; no PII fields exist |
| Explainability | SHAP drivers + reason codes + grounded narrative on every recommendation |
| Fairness | Per-archetype and rural-vs-urban error and stockout-reduction table; rural agents must not get worse service than the baseline |
| Security | Prompt-injection surface minimised (structured input only, numeric post-check); env-based secrets; input validation; CORS |
| Human oversight | Approve/Modify/Reject on every action; `NEEDS_EXTRA_FLOAT` always escalates; no automatic money movement |
| Transparency | UI separates prediction / assumption / AI-generated text; model card published |
| No harmful automation | The system recommends operational liquidity actions only. No credit decisions, no penalties for agents |

---

## 12. Success Metrics (KPIs) & Acceptance Criteria

| KPI | Target (test period incl. Eid 2026) |
|---|---|
| Stockout agent-days | ≥ 40 % reduction vs status quo |
| Failed cash-out value (৳) | ≥ 40 % reduction |
| Average idle cash | ≤ status quo (no "solve it by hoarding cash") |
| Rebalancing trips | ≤ +15 % vs status quo |
| Forecast WAPE (P50 CO) | ≥ 20 % better than seasonal-naive; ≥ 35 % on event days |

**Release (demo) acceptance:**
- All P0 requirements pass.
- `make test` is green.
- The demo script (§14) runs end to end offline in < 5 minutes.
- The metrics shown in the UI equal `artifacts/metrics.json` and the simulation output.

---

## 13. Scalability & Integration Path (post-hackathon)
1. **Data contract:** the `daily.parquet` schema maps 1:1 to an aggregated agent ledger (daily CO/CI per agent). No customer-level data is needed. **This is privacy-friendly by design.**
2. **Shadow mode:** run on governed, anonymised data from one distributor. Compare recommendations with actual DSO actions for 4–6 weeks.
3. **Pilot:** one distributor's DSOs use the DSO Plan before Eid. A/B test against control distributors on stockouts and failed value.
4. **Integration:** the API is consumed by the DSO app and agent app (push notification "keep ৳X cash tomorrow"). Nightly batch retrain. Drift monitoring per archetype.
5. **Governance:** model card, approval workflow, audit log, periodic fairness review.
6. **Scale:** a global model handles any number of agents (LightGBM trains on millions of rows in minutes); forecasts are precomputed nightly.

---

## 14. Demo Scenario (3–4 minutes)
1. **Hook (20 s):** "On Eid, an agent in Sylhet says 'cash nai'. The customer walks to a competitor. That happens thousands of times."
2. **Network Map (30 s):** the date is 2026-03-15, 5 days before Eid-ul-Fitr. Red clusters appear in rural Sylhet/Cumilla (cash) and urban Dhaka (e-float).
3. **Agent Detail (60 s):** a rural_remittance agent.
   - The forecast band jumps ×2.6 before Eid.
   - SHAP: `days_to_eid_fitr`, last-Eid multiplier.
   - Recommendation: TOP_UP_CASH ৳1,20,000 by Wednesday.
   - Bangla explanation. Click Approve.
4. **DSO Plan (30 s):** limited bag capacity. FloatWise prioritises by ৳ at risk.
5. **Impact (45 s):** backtest over Eid 2026 shows status quo vs FloatWise: stockouts −X %, failed ৳ −Y %, idle cash flat. Then the service-level slider.
6. **Responsible AI + scale (30 s):** human approval, fairness table, synthetic data, path to a pilot.

---

## 15. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Synthetic data too easy → judges doubt results | Realistic noise, shocks, censoring; show baselines doing OK in normal weeks; be honest about synthetic limits |
| Model doesn't beat baseline on events | "Event memory" features; check the generator; fall back to reporting the honest number |
| LLM hallucinates amounts | Numbers never come from the LLM; numeric post-check; template fallback |
| Frontend runs late | P0 screens 1, 3, 5 first; plain table instead of map if needed |
| No internet at venue | Cached narratives; local everything; pre-recorded demo video backup |
| Eid dates wrong | Dates in config; one-line fix |

---

## 16. Out of Scope
- Real money movement and integration with a real MFS core.
- Customer-level transactions or customer PII.
- Credit or lending decisions for agents.
- Route optimisation on real road networks (ordering only).
- Native mobile apps (a responsive web card instead).
- Hourly forecasting (P2 idea only).

---

## Appendix A — Mapping to Evaluation Framework

| Criterion (weight) | Where we score |
|---|---|
| Problem relevance (20 %) | Bangladesh-specific pain: Eid, garments, remittance; agent network is upay's core distribution |
| AI/ML depth (20 %) | Quantile LightGBM, leakage-safe multi-horizon features, censoring awareness, SHAP, optimization, grounded LLM |
| Business impact (20 %) | Backtest: stockouts, failed ৳, lost commission, idle cash, trips; per-1,000-agent extrapolation |
| Prototype quality (15 %) | Working end-to-end dashboard + API + approval flow, offline-safe |
| Innovation (10 %) | Moving-Eid-aware forecasting, two-sided (cash and e-float) risk, DSO capacity planning, Bangla agent card |
| Scalability & integration (10 %) | Aggregated-ledger data contract, shadow → pilot path, API-first |
| Responsible AI & security (5 %) | Human approval, fairness table, synthetic data, LLM guardrails |

## Appendix B — Bangladesh Calendar Defaults (approximate, editable in `config`)

| Event | 2024 | 2025 | 2026 |
|---|---|---|---|
| Eid-ul-Fitr | 2024-04-11 | 2025-03-31 | 2026-03-20 |
| Eid-ul-Adha | 2024-06-17 | 2025-06-07 | 2026-05-27 |
| Pohela Boishakh | 04-14 | 04-14 | 04-14 |
| Salary window | Days 1–10 each month (peak 5–8) | | |
