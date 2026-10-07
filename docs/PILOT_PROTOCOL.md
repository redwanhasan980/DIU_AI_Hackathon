# Partner validation and controlled pilot

Status: proposed, not conducted. Real customer/agent/transaction data stays out of this repository
(R-DATA-1). Partner analysis requires authorization, an isolated governed environment and data
owners' privacy/retention decisions.

## Establish the problem and upay priority

Interview agents and DSOs across rural remittance, garment, urban and market segments. Include
agents reporting zero failures. Record recruitment, dates and anonymized role/segment codes
outside this repo. Ask agents about refused transactions, recorded reasons, balances, recovery
time and alternative-agent use. Ask DSOs about delivery frequency, request lead time, bag/visit
limits, emergency trips and which decisions a plan would change. Ask the upay sponsor to rank
the workflow against current priorities and identify its operational owner and success criteria.

Collect aggregated daily measurements: pseudonymous agent/distributor/DSO IDs, segment,
requested/served cash-in/out counts and amounts, failures by liquidity reason, timestamped
balance observations, refill requests/arrivals, delivered amounts, visits, closures and outages.
Do not derive requested demand solely from served volume: denied demand is censored. Do not
collect customer names, phones or NIDs for forecasting.

## Shadow mode

Fit, validate and calibrate before an untouched future assessment window. Include a weekly cycle
and event period; determine duration and event availability with the sponsor. Replay features
at their original availability timestamps and separate outages/closures from liquidity failures.
Compare simple forecasts, quantiles/points, greedy/exact planning and status quo.

Report WAPE, pinball, width and coverage by event, horizon, rural/urban and capacity, including
sample sizes and confidence intervals clustered by distributor/day. Sparse segments require
more evidence. Record recommendations without changing deliveries; measure freshness, latency,
errors and missing agents. Review low-confidence/capacity-short cases before a pilot.

## Controlled operational pilot

Randomize at the **distributor** level to reduce DSO/nearby-agent spillovers. Match or stratify
clusters by geography, volume and historical failures. Control keeps its current workflow;
treatment receives human-reviewed recommendations. Freeze model/policy versions and metrics.
Include pre-event, event and post-event days. A statistician selects cluster count and duration
from measured baseline variance and a meaningful minimum effect; no powered sample is invented.

Primary outcome: liquidity-caused stockout agent-days per active agent-day. Report failed value
and failures per requested transaction separately, with intention-to-treat effects and cluster
confidence intervals. Do not replace them with adherent-agent-only claims.

Record advice shown, approval/modify/reject, actual delivery/self-rebalance and timing to measure
adherence. Track emergency visits, distance/time, staffing cost, cash carrying cost, extra float
and incidents. Reconcile realized fees net of commissions with the sponsor ledger, then subtract
delivery/holding/software costs before discussing net benefit.

Retention needs a separately governed analysis of unique customer cohorts and a pre-agreed
inactivity window. Failed transactions multiplied by 5% are not retention evidence. Exclude
churn from the main financial case until measured independently.

## Decision and rollback

Agree stockout improvement, cash/trip ceilings, coverage, fairness, freshness and security gates
before observing outcomes. Report null/negative results. Halt advice on missing/stale balances,
version errors, unreviewed drift, security incidents or material segment harm. Revert to the
existing DSO workflow and retain audit records. Operational review precedes resumption.

The completion record should link governed evidence owners, dates, fixed model/policy IDs,
sample, uncertainty intervals, incidents and sponsor sign-off. No interview, pilot or approval
is represented as completed here.
