# FloatWise — AI Agent Liquidity Forecaster

> AI Hackathon 2026 · DIU CPC × upay · Track 05: Merchant & Agent Intelligence

**FloatWise** predicts when upay agents will run out of **cash** or **e-float**, especially around Eid, garment salary days and remittance peaks. It recommends prioritised, human-approved rebalancing, so customers never hear *"cash nai, pore ashen"* ("no cash, come back later").

- Probabilistic 1–7-day demand forecasts per agent (LightGBM quantile models)
- Stockout risk + rebalancing recommendation (deterministic, explainable engine)
- DSO visit plan under cash-bag and visit capacity
- SHAP reasons + Bangla/English AI explanation (grounded, never decides amounts)
- Backtest: status quo vs FloatWise on stockouts, failed ৳, idle cash and trips
- 100 % synthetic data; human-in-the-loop by design

## Status
📐 Planning complete; implementation not started yet.

| Document | Purpose |
|---|---|
| [`docs/SRS.md`](docs/SRS.md) | Software Requirements Specification |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | Phased plan with checklists |
| [`CLAUDE.md`](CLAUDE.md) | Guide for AI coding agents |
| [`RULES.md`](RULES.md) | Mandatory project rules |

How to run, the results and screenshots will be added here as the build progresses.
