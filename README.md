# FloatWise — AI Agent Liquidity Forecaster

> AI Hackathon 2026 · DIU CPC × upay · Track 05: Merchant & Agent Intelligence

**FloatWise predicts when upay agents will run out of cash or e-float.** This matters most around Eid, garment salary days and remittance peaks. FloatWise tells the field team who to visit, how much to bring and why, so customers stop hearing *"cash nai, pore ashen"* ("no cash, come back later").

> All data is **synthetic** (see [`docs/DATA_ASSUMPTIONS.md`](docs/DATA_ASSUMPTIONS.md)). Every number below comes from `artifacts/*.json` produced by `make all`.

## Results (held-out test period: Jan–Jun 2026, including Eid-ul-Fitr and Eid-ul-Adha)

**Backtest: status quo vs FloatWise** (500 agents, same true demand for both):

| | Status quo (rule of thumb) | FloatWise | Change |
|---|---|---|---|
| Stockout agent-days | 6,736 | 3,730 | **−44.6 %** |
| Failed transaction value | ৳52.1 crore | ৳29.4 crore | **−43.6 %** |
| Lost agent + distributor commission | ৳31.1 lakh | ৳17.5 lakh | **−43.6 %** |
| Rebalancing trips | 49,362 | 51,280 | +3.9 % |
| Average cash held per agent | ৳3,51,692 | ৳3,60,630 | +2.5 % (honest trade-off) |

**Per 1,000 agents per month:**
- 996 stockout days avoided.
- 32,928 failed transactions avoided.
- ৳7.5 crore more transaction value served.
- ~1,600 customers retained.

These per-1,000 figures use illustrative business assumptions.

**Forecast accuracy (cash-out, WAPE, lower is better):**

| | FloatWise | Same day last week | 7-day average |
|---|---|---|---|
| All days | **18.6 %** | 39.6 % | 32.6 % |
| Eid days (−7…+3) | **20.6 %** | 58.9 % | 53.8 % |

**Fairness:** every area type improves, and none is worse than the baseline.
- Urban agents: −49 % stockouts.
- Rural agents: −33 %, because their total float is small for the Eid spike. That is what the "extra float" escalation is for.

**Known weakness:** P10–P90 coverage on Eid days is only 55 %; the model is over-confident at peaks. The policy compensates with a high service level, chosen on validation data. Details are in [`artifacts/model_card.md`](artifacts/model_card.md).

## What it does
1. **Forecasts** each agent's cash-out and cash-in demand 1–7 days ahead as P10/P50/P90. It uses global LightGBM quantile models with leakage-safe features: days to Eid, salary window, previous-Eid jump, recent volume and more.
2. **Decides** with a deterministic engine:
   - stockout probability, a top-up amount at a 99 % service level, or an escalation when even P90-level needs exceed the agent's float;
   - a **DSO visit plan** under a 10-visit, ৳10 lakh cash-bag limit.
3. **Explains**:
   - SHAP drivers in taka;
   - a short Bangla/English explanation. The LLM only rephrases structured facts, and a numeric guardrail plus template fallback mean it can never invent an amount.
4. **Keeps a human in the loop:** every action is Approve / Modify / Reject, and nothing moves money automatically.
5. **Proves impact** with a backtest simulator and a service-level trade-off curve.

```
synthetic data → features → LightGBM quantiles → decision engine → SHAP + LLM narrative → FastAPI → React → human approval
```

## Run it

Requirements: Python 3.11+, Node 20+. An LLM key is optional.

```bash
make setup     # Python venv + npm install
make all       # generate data, train, evaluate, backtest (~3 min)
make demo      # builds the web app and serves app + API on http://localhost:8000
```

For development, use two terminals: `make api` (port 8000) and `make web` (http://localhost:5173).

**Optional:** to get AI-written explanations, copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`. Then run `make narratives` to cache them for an offline demo. Without a key, the app uses the built-in Bangla/English templates.

## How to test it (checklist)
1. **Automated checks:** `make test` (83 backend tests) and `make lint`.
2. **Start the app:** `make demo`, then open http://localhost:8000.
3. **Network page:** it opens on **15 March 2026**, 5 days before Eid-ul-Fitr. Check the banner, the KPI tiles and the red risk map.
4. **Demo agent:** go to Risk list and open **AG00433 — Notun Bazar Store, Noakhali**. Check:
   - the ৳1,92,000 cash top-up;
   - the reason chips;
   - the 7-day outlook;
   - the forecast band against true demand;
   - the SHAP drivers;
   - the explanation.

   Switch the language to **বাংলা**.
5. **Decisions:** click **Approve**, then open the **Decisions** page to see it logged.
6. **DSO plan:** change *Max visits* or *Cash bag* and watch the route re-prioritise.
7. **Impact:** move the service-level slider and press *Re-run simulation*.
8. **Agent mobile card:** use the 📱 button on an agent page to see the Bangla card.
9. **Theme:** toggle dark mode (☾).
10. **Offline mode:** stop the API while `make web` is running. The demo pages still render from fixtures, and the header shows "Offline fixtures".
11. **Other dates:** try any date between 30 Jun 2025 and 30 Jun 2026 in the date picker.

## Repository map
| Path | What |
|---|---|
| [`docs/SRS.md`](docs/SRS.md) | Requirements, formulas, API and UI spec |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | Phased checklist (ticked as built) |
| [`docs/DATA_ASSUMPTIONS.md`](docs/DATA_ASSUMPTIONS.md) | Every synthetic and business assumption |
| [`CLAUDE.md`](CLAUDE.md), [`RULES.md`](RULES.md) | Guide and mandatory rules for AI coding agents |
| `backend/floatwise/` | `data/` → `features/` → `models/` → `engine/` → `simulation/` / `explain/` → `api/` |
| `backend/scripts/` | Experiments (censoring, quantile mode, policy tuning), narrative cache, fixture export |
| `frontend/src/` | React app: `pages/`, `components/`, `api/` (types + client), `i18n/`, `fixtures/` |
| `artifacts/` | metrics.json, model_card.md, simulation_default.json, fairness.json, experiment results |

## Responsible AI
- **Synthetic data only:** no personal data exists in the system.
- **Decisions vs explanations:** amounts and decisions are made by deterministic code; the LLM explains them.
- **Human approval:** every action needs Approve, Modify or Reject.
- **Fairness:** checked per area type and for rural vs urban.
- **Clear labelling:** the UI labels predictions, assumptions and AI-generated text separately.
- **Honest model selection:** censoring handling, quantile architecture and policy settings were all chosen on held-out periods, never on the test set (see the model card).

## Path to production
1. **Shadow mode:** run on governed, aggregated agent-ledger data from one distributor. Only daily cash-in/cash-out totals per agent are needed, with no customer-level data.
2. **Pilot:** use the DSO plan with one distributor before Eid and compare against control distributors.
3. **Integration:** send API output to the DSO app and agent app, with a nightly batch retrain and per-segment drift monitoring.
