# FloatWise — Synthetic Data Assumptions

Every number below lives in [`backend/config.yaml`](../backend/config.yaml) (rule R-DATA-3).

**This data is 100 % synthetic.** It is designed to reproduce *patterns* that MFS agents in Bangladesh plausibly experience. It does not reproduce any real company's volumes. No real people, phone numbers or businesses appear in it. Shop names are random combinations of generic words; district and upazila names are public geography.

Regenerate with `make data` (full: 500 agents) or `make sample` (50 agents, committed for tests). The same seed always gives identical files.

## 1. Network
| Assumption | Value | Why |
|---|---|---|
| Agents | 500 (sample: 50) | Big enough for a credible network view; trains in minutes |
| Archetype mix | urban 25 %, garment 20 %, rural remittance 30 %, market hub 15 %, university 10 % | Rural agents are the majority of an MFS agent network |
| Agent size | LogNormal(0, 0.35) multiplier | Real agents differ a lot in volume |
| Total float (cash + e-float) | U(1.4, 2.4) × (base CO + base CI) × size | Agents hold roughly 1.5–2.5 days of gross volume as working capital |
| Opening split | Cash share = base CO / (base CO + base CI) | Agents start roughly balanced for their own flow |
| DSO territory | ~25 agents per DSO within a district; 5 DSOs per distributor | Typical field-force span of control |
| Locations | District centre ± 0.12° jitter | Only for the map; not used by the model |

## 2. Calendar (Bangladesh)
| Assumption | Value |
|---|---|
| Eid-ul-Fitr | 2024-04-11, 2025-03-31, 2026-03-20 (approximate, moon-sighting dependent) |
| Eid-ul-Adha | 2024-06-17, 2025-06-07, 2026-05-27 (approximate) |
| Ramadan | The 29 days before Eid-ul-Fitr |
| Eid holiday | Eid day + 2 days; "post-Eid" = days 3–7 after |
| Pre-Eid ramp | Demand rises over the 10 days before Eid; ramp (k = 1..10 days before) = 1.0, 1.0, 0.9, 0.75, 0.6, 0.45, 0.35, 0.25, 0.15, 0.1 |
| Salary window | Days 1–10 of each month, curve 0.3 → 1.0 (days 5–7) → 0.3; garment wages are paid within the first ~7 working days |
| Allowance disbursement (G2P) | **Synthetic** quarterly schedule on 20 Jan / Apr / Jul / Oct, effect over the disbursement day + 4 days (curve 1.0 → 0.2). upay disburses government social-safety-net allowances; recipients, mostly rural, then cash out at agents. The real schedule is set by the government; replace these dates with it |
| Weekend | Friday and Saturday |
| Pohela Boishakh | 14 April and the 2 days before |
| Public holidays (fixed) | 21 Feb, 26 Mar, 1 May, 16 Dec |

**Key insight:** Eid moves about 11 days earlier every Gregorian year. A "same month last year" rule therefore misses it, while a model with `days_to_eid` features can learn it.

## 3. Demand model (true demand, per agent per day)
```
demand = base[archetype] × size × dow × (1 + salary_amp × salary_curve) × (1 + g2p_amp × g2p_curve)
         × (1 + eid_amp × pre_eid_ramp) × eid_holiday/post_eid × ramadan × boishakh × holiday
         × shock(district, day) × (1 + 12 %)^years × LogNormal noise (mean 1)
```
| Archetype | Base CO / CI per day (৳) | Noise σ | Signature (CO = cash-out, CI = cash-in) |
|---|---|---|---|
| urban_residential | 1,50,000 / 1,80,000 | 0.22 | CI ×2.4 before Eid-ul-Fitr (people send money home); CI +35 % at month start |
| garment_belt | 2,50,000 / 1,00,000 | 0.22 | CO ×2 at salary peak; CO ×2.2 before Eid-ul-Fitr (bonus); Friday −30 % |
| rural_remittance | 80,000 / 40,000 | 0.25 | CO ×2.6 before Eid-ul-Fitr, ×2.3 before Eid-ul-Adha; stays high after Eid; CO ×1.8 on allowance (G2P) disbursement days |
| market_hub | 3,00,000 / 3,00,000 | 0.20 | Big both ways; Boishakh ×1.3; pre-Adha cattle-market CO ×2 |
| university_area | 60,000 / 50,000 | 0.25 | CO +50 % at month start (family support); weekends −20/−40 % |

Further assumptions:
- **Eid holiday multipliers:** 0.3–0.35 in cities (people leave) and 0.8 in rural areas. Post-Eid: 0.6–0.8 in cities, 1.1 in rural areas.
- **CO/CI noise:** correlated with ρ = 0.5 (busy days are busy both ways).
- **Growth:** 12 % per year (MFS volume growth).
- **Ticket size:** mean ৳1,500–৳3,000 by archetype, with ±10 % noise. Counts = amount / ticket.

## 4. Shocks (ground truth in `shocks.csv`)
14 random events, cycling through these types:

| Type | Effect | Duration | Season / districts |
|---|---|---|---|
| Flood | ×0.5 | 3–7 days | Jun–Sep; Sylhet, Moulvibazar, Feni, Noakhali, Barishal, Rangpur |
| Network outage | ×0.3 | 1 day | Any month; any district |
| Hartal | ×0.6 | 1–2 days | Oct–Mar; Dhaka, Chattogram, Rajshahi, Khulna |

## 5. Ledger mechanics
- A cash-out moves value from agent cash to agent e-float; a cash-in does the reverse. **Total float is conserved.** Rebalancing only converts between the two.
- Each day is simulated in 4 slots:
  - Cash-outs skew to the morning (35/30/20/15 %).
  - Cash-ins skew to the evening (15/25/30/30 %).
  - Cash-outs are served first in each slot.
- A transaction that the balance cannot cover is **unserved** (a failed transaction). Observed data contains only served amounts, as in reality. True demand is kept separately and used only for evaluation and simulation (R-ML-6).
- Rebalancing decided at the close of day *t* takes effect at the opening of day *t + 1* (lead time 1 day).

## 6. Status-quo policy (what agents do today)
Each evening, an agent:
1. Computes `target = 1.5 × mean served volume of the last 7 days`, separately for cash (from cash-outs) and e-float (from cash-ins).
2. If cash < 0.6 × cash target, converts e-float to bring cash to the target the next morning.
3. Otherwise, if e-float < 0.6 × e-float target, does the reverse.

A trailing average lags behind sudden spikes, which is the weakness FloatWise targets.

**Resulting status-quo stockout rates (full dataset):**
- Normal days: 0.4–3 % of agent-days.
- Pre-Eid days: 20–40 % for garment and rural agents.
- Urban agents: they convert cash to e-float during the pre-Eid cash-in rush, then often run out of cash on Eid day itself.

## 7. FloatWise operating assumptions (backtest)
| Assumption | Value | Why |
|---|---|---|
| DSO capacity | 10 visits and ৳10,00,000 cash bag per DSO per day | Typical field visit load |
| App-advice compliance | 70 % of agents not visited by a DSO follow the in-app advice and self-rebalance at the distributor point (as agents already do today); 30 % keep their own rule | Conservative; adoption is never 100 % |
| Lead time | Advice at close of day *t* is executed at the opening of *t + 1* | Same as status quo |
| Policy defaults | Service level 0.99, risk threshold 0.10 | Selected on the validation period (`scripts/tune_policy.py`, `artifacts/policy_tuning.json`) |
| DSO route allocator | Exact (knapsack) optimiser; practically equal to greedy | Selected on the validation period (`scripts/compare_allocators.py`) |

## 8. upay alignment: public facts and remaining assumptions
These values come from upay's published tariffs and press coverage (checked October 2026). **Verify them with upay before any real use**: tariffs change.

| Item | Value used | Source |
|---|---|---|
| Customer cash-out fee at an agent | Primary wallet **1.4 %**, salary wallet **1.0 %**, remittance wallet **1.0 %**, disbursement (G2P) wallet **0.7 %** | upay limits & charges ([UCB upay docs](https://www.ucb.com.bd/reports/downloads/Upay/Upay%20Limits%20and%20Frequencies.pdf)); [Financial Express, 2021](https://today.thefinancialexpress.com.bd/stock-corporate/upay-offers-lowest-cash-out-charge-in-mobile-money-transactions-1619026261) |
| Fee by area type | Urban, market, university: 1.4 % (primary). Garment belt: 1.0 % (salary wallet). Rural remittance: 1.1 % (blend of remittance, G2P and primary wallets: **assumption**) | Derived from the row above |
| Agent commission | **0.41 %** of each cash-in and cash-out amount | upay agent information ([upaybd.com](https://www.upaybd.com/services/details/upay-agent)) |
| Distributor commission | **0.10 %** of each cash-in and cash-out amount | Same |
| upay's net margin on a cash-out | Fee − 0.51 % (e.g. 0.89 % on the primary wallet) | Derived |
| Cash-out at UCB ATMs | 0.8 % (not modelled; a possible overflow channel when an agent is short) | [TBS, 2021](https://www.tbsnews.net/companies/upay-rolls-out-its-lowest-cash-out-charge-atms-244996) |
| Customer cash-out limits | ৳50–25,000 per transaction, ৳25,000 per day, ৳1,50,000 per month (upay); Bangladesh Bank's 2025 cap is ৳30,000 per day | upay limits & charges; [TBS, 2025](https://www.tbsnews.net/economy/mfs-transaction-limit-refixed-daily-maximum-cash-tk50000-cash-out-tk30000-1103256) |
| Network size | ~1,54,000 retail agents, ~85 lakh customers (end of 2023) | [TBS, 2024](https://www.tbsnews.net/economy/stocks/upays-accumulated-losses-cross-tk300cr-2023-877946) |
| Services that move agent liquidity | Cash-in, cash-out, salary disbursement, inward remittance, government allowance (G2P) disbursement | upay service list ([Google Play](https://play.google.com/store/apps/details?id=bd.com.upay.customer&hl=en)) |

**How these values are used:**
- Synthetic ticket sizes (৳1,500–৳3,000 mean) sit well inside the per-transaction limits.
- The backtest reports three kinds of loss on failed transactions:
  - lost **upay fee revenue**: fee − agent − distributor commission, on failed cash-outs;
  - lost **agent + distributor commission**: 0.51 % on failed cash-ins and cash-outs;
  - **customers at risk**.
- These are then scaled to upay's network size.

**Still assumptions (no public source):**

| Assumption | Value |
|---|---|
| Probability a customer leaves after a failed cash-out | 5 % |
| Opportunity cost of idle cash | 10 % per year |
| Daily volumes per agent, area mix, Eid / salary / G2P multipliers | Sections 1–4 |
| G2P disbursement dates | Synthetic quarterly schedule |

## 9. Known limitations
- Daily granularity with a fixed intraday profile; real intraday patterns vary by agent.
- The forecasts used in the backtest are computed from status-quo-world history. In the FloatWise world, fewer stockouts would make observed history slightly *higher*. This makes our results slightly conservative.
- Customers do not move to a neighbouring agent when one stocks out. Spill-over is not modelled.
- Eid dates are approximate and must be checked against the official announcement.
- **Checked 3 October 2026:** Bangladesh celebrated Eid-ul-Fitr on **21 March 2026** ([The Daily Star](https://www.thedailystar.net/news/bangladesh/news/bangladesh-celebrate-eid-ul-fitr-march-21-4132701)) and Eid-ul-Adha on **28 May 2026** ([Prothom Alo](https://en.prothomalo.com/bangladesh/vdn1tkv26i)), one day after the dates in `config.yaml` (20 March, 27 May). The 2024 and 2025 dates match. The synthetic results are internally consistent; correct the 2026 dates and re-run the pipeline before any real use.
- **Checked 3 October 2026:** the agent (0.41 %) and distributor (0.10 %) commission rates could not be re-confirmed on a public upay page. Confirm them with upay; they drive the commission figures and upay's net fee.
