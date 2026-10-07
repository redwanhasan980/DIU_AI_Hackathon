# Local integration demonstration

This is an implemented local integration contract and operational workflow using **simulated upstream transactions and a simulated DSO system**. It is not connected to upay. SQLite is the local durable store; it is not a claim of production database deployment. There is no money movement.

## Start and demonstrate

```bash
python run.py integration-setup
python run.py demo
```

`demo` builds the frontend and starts the API and a separate queue worker. Existing viewer/operator/admin passwords are preserved. For development use `python run.py dev`. If starting FastAPI directly, run `python run.py integration-worker` in a second terminal. `make demo` also starts both processes.

1. Sign in as **admin**, open **Integration** (`/integration`), keep the demo date `2026-03-15`, and select `AG00471`.
2. Click **Start feed**. The worker submits deterministic transactions through the authenticated HTTP ingestion endpoint. Watch receipts progress from pending to processed. Pause/resume demonstrates a persisted connector cursor.
3. The feed sends served cash-in/cash-out, a liquidity denial, a balance snapshot, then day closure. The projected day replaces the original synthetic daily row; it is not added to it. Earlier baseline history remains the seed. A forecast waits for completed history.
4. After the feed completes and pending events reach zero, click **Refresh** under the live recommendation. Show forecast origin, history/balance revisions, model version and policy version. Open the agent page or DSO plan to show the same revised recommendation inputs.
5. Click **Approve and create DSO task**, then **Dispatch**, **Accept**, and **Simulate confirmed delivery**. The worker matches the delivery to the approved exchange and saves the post-delivery observation before marking the task completed. Refresh the recommendation to show the new balances and risk.
6. Click **Replay same events**. It resubmits the same event IDs and payloads. Event counts and served totals do not increase. A new simulation for an already projected day is blocked; select another agent/date for a new run.
7. Show worker heartbeat, pending/failed counts, lag, inference latency/errors, forecast age alerts, model registry and distribution monitor. The monitor reports insufficient data until the configured number of completed days exists.
8. Sign in as **operator**: approval, task creation and delivery workflow work; connector, manual ingestion and retry controls are hidden and forbidden by the API. A **viewer** can inspect the demonstration but cannot mutate it.

If a recommendation requires extra float, show its human escalation on the agent page or choose another agent/date for the exchange demonstration. The DSO simulator handles `TOP_UP_CASH` and `TOP_UP_EFLOAT`; it does not invent extra capital.

## Versioned ingestion contract

`POST /api/v1/integration/events` accepts one event per request. The configured connector bearer credential is scoped only to this endpoint. Browser admin requests use the existing cookie session and CSRF header. Credentials are stored only in ignored `.env`, never in browser fixtures.

```json
{
  "schema_version": 1,
  "source": "simulated-upstream",
  "event_id": "example-agent-day-001",
  "occurred_at": "2026-03-15T12:00:00+06:00",
  "agent_id": "AG00471",
  "payload": {
    "kind": "transaction",
    "side": "cashout",
    "outcome": "served",
    "amount": 1000
  }
}
```

Event payloads:

| Kind | Fields | Meaning |
|---|---|---|
| `transaction` | side, outcome, integer amount, optional failure_code | Served amount contributes to history; only liquidity denials contribute to stockout flags. Denials require a failure code: liquidity/network/identity/limit. |
| `balance_snapshot` | integer cash, efloat, increasing sequence | Authoritative observation; cash + efloat must conserve the synthetic capacity. |
| `day_closed` | kind only | Marks the agent day complete after a balance exists. |
| `delivery_confirmation` | task_id, reference, cash, efloat | DSO-source confirmation plus reconciled post-delivery balance. |

Days use Asia/Dhaka boundaries. Unknown agents, dates outside the demo window, future timestamps, unexpected fields, invalid amounts and source/type mismatches are rejected. Duplicate source/event IDs return the existing receipt; changed payloads with the same ID return 409.

A late transaction reopens its day and changes the agent revision. Forecasts and approvals are blocked until another day-close event is processed. Previously created tasks retain their original provenance and cannot be dispatched/completed after their inputs change. Pending events also block approvals and dispatch. Operators cancel obsolete tasks and review fresh recommendations.

`GET /integration/status` returns the connector, worker, metrics, model registry, drift state, latest 50 receipts and latest 50 tasks. `POST /integration/events/{id}/retry` is admin-only. Receipt status is acknowledgement of processing, not proof of money transfer.

Tasks use `POST /integration/tasks` with a persisted approved `decision_id`; creation is idempotent by decision. `POST /integration/tasks/{id}/status` requires `expected_version`. Dispatch enforces configured DSO daily visit and cash-bag limits. `POST /integration/tasks/{id}/simulate-delivery` requires a current accepted task and creates a queued simulated observation. Completion happens in the worker transaction, with reconciliation and audit. No generic endpoint allows setting `completed` directly.

## Persistence and recovery

Events, aggregates, balances, inference results, connector cursors, task versions, model selection and audit records share the ignored `artifacts/operations.sqlite3` database. SQLite WAL supports concurrent readers; immediate write transactions serialize mutations. Event projection, revision advancement and acknowledgement commit together. Inference runs after projection; a worker restart recovers closed days whose forecast was not generated. Failed events retain error details and can be retried with an audited admin action.

Do not delete this database to replay a demonstration: it also stores sign-in sessions and previous operational records. Replay is built into the connector.

## Model lifecycle

```bash
python run.py models list
python run.py models retrain
python run.py models register --directory artifacts/model_candidates/CANDIDATE --evaluation artifacts/model_candidates/CANDIDATE/evaluation.json
python run.py models activate --version MODEL_VERSION --reviewed
python run.py models rollback --reviewed
```

Retraining writes an isolated candidate directory; it does not replace the running model or original benchmark artifacts. Fit, early stopping and assessment use separate configured 2025 windows. The candidate is evaluated against simple baselines with overall/event/rural/urban interval checks. The 2026 final test is not reused for tuning.

**Current data limit:** the original incumbent was fitted/early-stopped beyond that 2025 assessment period. Consequently, retraining reports an unavailable honest incumbent comparison and blocks promotion until a fresh future holdout exists. It does not compare the incumbent on its training dates and call that a valid promotion gate. Registry/activation/rollback code is implemented, but no new model is claimed promoted by this change. Reviewed activation also verifies model/schema hashes and temporal eligibility. Promotion remains manual.

A scheduler can invoke the same retraining command; no unattended scheduler or automatic promotion is enabled in this local demo. Process-level model version selection is synchronized from the database; requests encountering changed inputs return a conflict and require refresh. Original model evaluation/simulation pages remain historical evidence for their stated model versions.

## Monitoring and benchmark

Configuration lives in `backend/config.yaml` under `integration`: worker polling/retries, connector speed/volume multiplier, historical stockout example amount, minimum drift sample count, mean-ratio threshold, coverage tolerance and freshness alert budget. All thresholds are demonstration settings, not validated partner SLAs.

Distribution monitoring compares completed replay days' served amounts, normalized by prior 28-day agent volume, with the synthetic training reference. Small samples are explicitly inconclusive. This monitor does not estimate realized forecast accuracy from censored served transactions or measure real business benefit.

```bash
python run.py integration-benchmark
# Smaller explicitly requested benchmark:
python run.py integration-benchmark --populations 500 --batch-size 256
```

The benchmark uses isolated temporary databases and replicated synthetic histories for 500, 10,000 and 50,000 agents. It measures actual schema validation/local receipt writes, worker projection, complete historical feature construction, batched inference and grouped DSO planning. It records elapsed seconds, events/second, failures, batch size, hardware and model version in `artifacts/integration_benchmark.json`. It excludes HTTP concurrency, broker infrastructure, production DB performance and retraining. No new scale result is claimed until the command is run.

## Acceptance scenarios to verify

- Completed-day replay changes observed history and produces live forecasts used consistently by agent/network/DSO views.
- API/worker restart preserves pending events, connector cursor, forecasts, approvals and completed tasks.
- Identical replay changes neither event count nor aggregate totals; conflicting identity returns 409.
- Late transaction requires reclosure/recalculation; an old approval/task is rejected.
- Snapshot sequence errors retry within configured bounds and remain visible; admin retry is audited.
- Delivery with wrong balance/agent/date cannot complete; the same confirmation cannot apply twice.
- Concurrent task updates require the correct version; DSO dispatch respects bag and visit limits.
- Viewer/operator/admin and connector service permissions are enforced at the API.
- Failed candidate evaluation blocks activation; eligible reviewed activation invalidates old provenance; rollback selects the recorded previous model.

These are acceptance scenarios, not a claim that runtime tests or the scale benchmark have been executed.
