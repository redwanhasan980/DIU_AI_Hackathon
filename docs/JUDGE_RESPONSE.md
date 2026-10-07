# Response to Phase 1 judge feedback

No real upay outcomes, interviews or field pilots are claimed. The submitted model and 2026
impact artifacts remain historical synthetic results.

| Criterion | Change available for review | Evidence still required |
|---|---|---|
| Problem relevance | Independent survey below; [pilot protocol](PILOT_PROTOCOL.md) | Current upay stockouts, failed value, DSO priorities and acceptance |
| AI/ML depth | `make validate`: event/horizon conformal intervals, retrained feature ablations, baselines and demand shifts | Governed real-data calibration, event transfer and censoring validation |
| Business/customer impact | Simulations and retention proxies labelled; adherence × churn sensitivity | Actual adherence, unique retention, realized fees and operating costs |
| Prototype quality | Live inference, persistent synthetic balance observations, recalculation, transactions, audit, idempotency and version conflicts | Partner ingestion, parallel HTTP load and production operational use |
| Innovation | Quantiles vs median-only; exact vs greedy; no DSO visits; no same-day inflow credit; simple forecasts through the engine; feature removals | Real incremental/causal value; no novel-algorithm claim |
| Scalability/integration | Computation benchmark through 154,000 replicated agents; implemented [local event/DSO workflow](INTEGRATION_DEMO.md), monitoring and model registry | Real upay connection, production broker/database, independent-agent scale and full HTTP workload; new complete-pipeline benchmark pending execution |
| Responsible AI/security | Password login, session cookies, server roles, operational access controls, local demo, durable audit, rate/body limits, approval checks and protected offline behavior | upay identity, tenant/DSO scopes, tamper-resistant audit, security/privacy review and real-data fairness |

## Independent problem evidence

The [MicroSave / Helix Agent Network Accelerator Bangladesh survey (2016)](https://www.microsave.net/wp-content/uploads/2016/08/180709-Bangladesh-Country-Report-2016.pdf)
reports nationally representative interviews with 2,088 agents (slide 8). Slide 24 reports
99% receiving delivered liquidity, with medians of 15 e-float and 10 cash deliveries per month.
It also reports a median of **zero transactions denied per day**.

Slide 25 discusses fluctuating customer demand and cash-delivery delays as liquidity-management
barriers and recommends models of agent float requirements based on transaction history.
This supports the forecasting use case, without establishing current upay stockout frequency.

This supports liquidity delivery as an established operational workflow and challenges the
assumption that stockouts are widespread on ordinary days. It is historical, covers multiple
providers, and predates upay; it cannot validate present upay or event-specific failures.
FloatWise's priority for upay remains a hypothesis: improve delivery timing and prioritization
under limited DSO capacity during peaks. Validate it using current agent failure reasons and
distributor interviews before deployment.

## Experiment protocol

All cutoffs and scenarios live in `backend/config.yaml → validation`:

1. Fit through December 2024; January–February 2025 is used only for early stopping.
2. Calibrate on March–15 April 2025, including Eid-ul-Fitr, using uncensored served labels.
   Served volume cannot stand in for latent demand on stockout days.
3. Assess on 16 April–June 2025, including Eid-ul-Adha. Target dates are disjoint. Assessment
   histories may include already observed calibration days; the 2026 test is never used.
4. Retrain feature ablations with identical fit/early-stop boundaries and seed.
5. Compare planning variants using identical balances, demand and compliance random draws.
6. Apply cash-out/cash-in surges, heavier noise and displaced demand to fixed forecasts.
   This tests exogenous sensitivity, not independent field data or a closed-loop deployment.

`artifacts/judge_validation.json` contains coverage, width, pinball, WAPE, horizon/area slices,
ablation outcomes and sensitivity. `artifacts/scale_benchmark.json` records repeats, machine,
batch size and raw timings. The Validation evidence page reads these generated artifacts.
The [generated results summary](../artifacts/judge_validation_summary.md) presents the measured
comparisons and explicitly reports the remaining event coverage failure.

Intervals expand without changing P50. Temporal dependence, censored samples and event shift
can defeat coverage. The candidate calibrator is **not promoted** into the submitted model.
Coverage improvement alone is insufficient: review width, pinball, fairness and planning costs.
`no_same_day_inflow_credit` removes the engine overlap assumption, not physical ledger cash-in.
Stockout-history removal tests censored-history information, not latent-demand recovery.
Simple forecast comparisons also include empirical residual intervals fitted on the same
uncensored calibration observations, alongside the deliberately collapsed point-only arms.
These provide a fairer uncertainty-aware baseline than treating a simple forecast as certain.

## Demonstration and controls

```bash
python run.py validate
python run.py benchmark
python run.py fixtures
python run.py demo
```

Open Validation evidence for comparisons. In Live operations demo, load a synthetic agent,
change its cash/e-float split and save. Recommendations and DSO plans recalculate. Restart the
API and reload to show persistence. `Run model now` executes six boosters instead of reading
forecast artifacts. Its features use the existing synthetic served-volume ledger; balance
observations affect the engine, not historical features or weights.

`FLOATWISE_AUTH_MODE=demo` allows direct loopback transport only. Never expose it through a
proxy: the API sees the proxy's local address and ignores forwarding headers. External access
requires `FLOATWISE_AUTH_MODE=required` and TLS.

Run `python run.py auth-setup` to create local viewer/operator/admin username/password accounts.
Initial passwords are shown once; only salted PBKDF2 hashes are kept in ignored `.env` under
`FLOATWISE_USERS`. The UI signs in through a rate-limited endpoint and uses an HttpOnly cookie.
Sessions are stored as hashes in SQLite, expire after eight hours by default, survive restart,
and are revoked on logout or account password change. CSRF headers and Origin checks protect
cookie-authenticated mutations. Production still requires the sponsor identity provider and lifecycle controls.

| Role | Permission |
|---|---|
| viewer | Read forecasts, recommendations, plans, impact and decision summaries |
| operator | Viewer plus simulation and recording human decisions |
| admin | Operator plus live inference, observations and audit |

Roles are network-wide; there is no tenant/DSO ownership boundary yet. The UI uses an HttpOnly session cookie and clears the input after connecting. Auth/permission/rate errors never use fixtures.
Production builds require a live API unless offline demo mode is explicitly enabled. Writes
never fall back to fixtures.

SQLite WAL coordinates connections/processes. Decisions and audit commit together.
`Idempotency-Key` deduplicates a retry and returns 409 if reused with different content.
Balance observations compare `expected_version` inside the write transaction and conserve
synthetic float. Audit is append-only via this API, not tamper-resistant against administrators.
Concurrency tests cover durable cross-connection writes and API behavior, not production load.

## Remaining rollout gates

- Current agent/DSO problem validation and sponsor acceptance.
- Authorized anonymized data in a governed environment, outside this public repo.
- Real-data event reliability and fairness acceptance.
- Controlled distributor pilot with measured costs/adherence.
- Sponsor identity/ownership authorization, production database/broker and real upay adapter. Local simulated event pipeline and DSO workflow are implemented.
- Security review and operational rollback drill.

Code changes alone cannot satisfy gates requiring partner data or field operations.
