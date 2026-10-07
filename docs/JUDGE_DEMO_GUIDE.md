# Judge-feedback demonstration guide

Use this as an 8–10 minute walkthrough. Application: http://localhost:8000.
The generated experiments already exist; avoid rerunning training or benchmarking during the pitch.

## Preparation

- Set the decision date to **2026-03-15** and the language to English. Show Bangla briefly later.
- Keep the usernames/passwords from local setup available privately. Do not put them on public slides.
- Open the [feedback response](JUDGE_RESPONSE.md), [generated results](../artifacts/judge_validation_summary.md),
  [pilot protocol](PILOT_PROTOCOL.md) and [production architecture](PRODUCTION_ARCHITECTURE.md).
- Use sequential sign-out/sign-in for role changes. Tabs in one browser profile share a session;
  use different browser profiles for simultaneous role comparisons.
- For the live demonstration, use **AG00471**. Note its original cash balance before editing,
  and restore that value after the demonstration. E-float adjusts to conserve total float.

## Opening — 20 seconds

> We retained the original forecasting prototype and added explicit validation experiments,
> live model execution, persistent operations, role-based login, and a controlled pilot plan.
> Our impact remains simulated; we have not measured upay production outcomes.

## 1. Responsible AI and security — 1 minute

**Judge request:** authentication, role authorization, audit and privileged-action controls.

1. Sign in at `/login` as **viewer**. Point to the verified account/role in the header.
2. Open `/agents/AG00471`: forecasts and recommendations are readable, approval controls are absent.
3. Open `/operations`: the page explains that admin access is required.
4. For server enforcement, open `/api/v1/operations/audit` in another tab while still a viewer:
   the API denies access, independently of the navigation controls.
5. Sign out and sign in as **operator**: approval controls become available; Operations remains restricted.
6. Sign out and sign in as **admin**: Operations is available. Refresh to show the session persists.

**Say:** Passwords are hashed, cookies are HttpOnly, sessions expire and are revoked on logout.
The API enforces roles, request/body limits and CSRF checks. Roles currently apply across the
synthetic network; sponsor identity and DSO ownership controls remain future integration work.

Do not claim a production security review or external identity-provider integration.

## 2. Prototype quality — 2 minutes

**Judge request:** live recalculation and persistent state rather than only precomputed artifacts.

1. As admin, open `/operations`, enter **AG00471**, and click **Load balances**.
2. Note the original cash, e-float and balance version.
3. Click **Run model now**. Show the generated chart and its **live** source/model version.
   This runs the loaded LightGBM models using the existing historical synthetic ledger.
4. Open `/agents/AG00471` in another tab and note its balances, stockout risk and recommendation.
5. In Operations, set cash to **0** and click **Save synthetic balances**. Show the incremented version.
   Total cash plus e-float is conserved.
6. Refresh the agent tab. Show the saved balances and recalculated risk/recommendation.
   DSO plans also read the updated operational state; open the agent's DSO link if its eligible action changes.
7. Reload Operations, load the same agent again, and show the saved state remains.
8. Restore the original cash balance and save. Reopen the agent page after restoring.

**Say:** Balance observations change the decision engine's current inputs. They do not rewrite
historical transactions or retrain the forecasting model. Forecast execution and operational
recalculation are separate demonstrations.

### Optional concurrency proof — 30–45 seconds

Open Operations in two tabs and load the same agent/date in both. Both initially show the same
version. Save a change in tab A; then attempt a save in tab B without reloading its balance.
Show the stale-version conflict. Reload tab B before retrying, and restore the original cash.
This demonstrates lost-update protection, not production concurrency or load capacity.

## 3. Human approval and durable decisions — 45 seconds

Open `/agents/AG00471` after restoring its balance. If it has NO_ACTION, select another agent
needing action from `/risk`. Click Approve, Modify or Reject, then open `/decisions`.
Refresh and show the recorded decision. Open `/api/v1/operations/audit` as admin for the audit trail.

**Say:** Approval records a human decision and never moves money. Decision writes have
idempotency and balance-version checks; decision and audit storage are transactional.

## 4. AI/ML depth and innovation — 2 minutes

**Judge request:** event-day calibration, demand-shift robustness, feature contributions and
evidence for the complete pipeline compared with simpler alternatives.

Open `/validation` and scroll through:

| Section | What to explain |
|---|---|
| Interval calibration | Separate 2025 calibration and assessment windows; no tuning on the submitted 2026 test |
| Feature ablations | Models retrained with calendar, event-memory or stockout-history groups removed |
| Pipeline ablations | Full pipeline compared with median-only forecasts, greedy allocation, no DSO visits and simple forecasting baselines |
| Demand-shift stress | Frozen forecasts evaluated against cash-out/cash-in surges, heavier noise and shifted event demand |

**Be precise about calibration:** In the candidate 2025 fold, event cash-out coverage improves
from **47.5% to 66.6%**, but still fails the **72–88%** acceptance band. The candidate has not
been promoted. This is a separate experiment; it does not revise the original model's approximately
60% event coverage on the 2026 test.

**Be precise about innovation:** Compare against the empirical-interval simple baselines as well
as point-only models. In this assessment, trailing-mean forecasting with empirical intervals is
competitive, and exact allocation differs only slightly from greedy allocation. The experiments
quantify component value and limitations; they do not establish a novel algorithm or real causal benefit.

Open `/model` briefly to show the retained temporal evaluation, baselines and segment fairness.
On the agent page, show SHAP drivers and the bilingual explanation with deterministic amounts.

## 5. Business/customer impact — 1 minute

**Judge request:** distinguish simulated impact from validated operations; examine adherence/churn assumptions.

1. Open `/impact`. Point to the explicit synthetic simulation and illustrative network labels.
2. Show the original six-month **47.5% stockout reduction** and **53.7% fee-loss reduction**.
3. Explain the accompanying trade-offs: average cash held increased **2.3%** and trips increased **4.1%**.
4. Return to `/validation` and show the **Adherence and churn sensitivity** table.

**Say:** These are backtest results. Network figures are extrapolated scenarios, and customer
retention is a failure-count proxy. We now vary adherence and churn assumptions instead of treating
them as measured behavior. Actual costs, realized fees, unique retention and adherence need a pilot.

## 6. Scalability and integration — 45 seconds

**Judge request:** larger populations and a defined production ingestion/serving/monitoring path.

At the bottom of `/validation`, show 500, 10,000, 50,000 and 154,000 replicated synthetic profiles.
The 154,000-row benchmark records approximately **78.0 seconds for seven-day inference** and
**15.69 seconds for planning** on the benchmark machine.

Open [PRODUCTION_ARCHITECTURE.md](PRODUCTION_ARCHITECTURE.md) for ingestion, retraining,
versioning, drift monitoring and sponsor integration design.

**Say:** This is a computation benchmark using replicated feature rows and balances. It excludes
full feature construction at scale, streaming, database/HTTP load, concurrent serving and retraining.
The production integration pipeline is designed, not connected to upay.

## 7. Problem relevance and rollout plan — 45 seconds

Open [JUDGE_RESPONSE.md](JUDGE_RESPONSE.md), under Independent problem evidence.
Show the linked historical independent agent survey and the limitations documented alongside it.
It supports an established liquidity-delivery workflow; it does not validate current upay stockouts.
The survey's low reported ordinary-day failures are explicitly acknowledged.
Show slides 24–25: liquidity delivery and reported failures, followed by demand/delivery barriers
and the report's recommendation to model float requirements from agent transaction history.

Open [PILOT_PROTOCOL.md](PILOT_PROTOCOL.md) and point to:

1. Current agent/DSO interviews and sponsor confirmation of operational priority.
2. Aggregated failures, balances, refill/delivery timings and reason codes.
3. Shadow-mode comparison on governed data, including an event period.
4. A distributor-level controlled pilot measuring actual adherence, costs, fees and failures.
5. Pre-agreed reliability/fairness/security gates and rollback criteria.

**Say:** The remaining validation needs partner evidence. Interviews, real-data evaluations,
controlled pilots and sponsor integration have not been completed.

## Closing — 15 seconds

> We can now demonstrate live execution and persistent operational controls, and show reproducible
> experiments for model calibration, component value, assumptions and compute scale. The remaining
> gates are current upay problem validation, reliable real-data performance and a controlled field pilot.

## Suggested submission evidence

- An 8–10 minute recording following this sequence.
- Screenshots of login/roles, live Operations, a recorded decision, calibration/ablations and scale timings.
- The feedback-to-change matrix in [JUDGE_RESPONSE.md](JUDGE_RESPONSE.md).
- The [generated results summary](../artifacts/judge_validation_summary.md) with underlying JSON artifacts.
- The pilot protocol and production architecture, clearly marked proposed/design work.

Keep numeric claims tied to generated artifacts, and keep credentials out of the public recording.

## Integration readiness addendum

The earlier balance-only demonstration remains available. For the new complete transaction-to-delivery workflow, use [INTEGRATION_DEMO.md](INTEGRATION_DEMO.md): open `/integration`, start the HTTP feed, wait for day closure and live inference, approve, dispatch, accept and submit a simulated delivery. Show persisted receipts, revisions, reconciliation, deduplicated replay, worker telemetry and the model registry. A new complete-pipeline benchmark command exists, but its results are not claimed before execution. Production/upay connection and real outcomes remain pending.
