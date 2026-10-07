"""SQLite event projection and operational workflow; no money movement.

The queue is consumed by a separate worker. Projection commits precede inference, so
an interrupted inference remains dirty and can be recovered after restart.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
import uuid
from typing import TYPE_CHECKING

import numpy as np

from floatwise.api.persistence import Conflict, encode
from floatwise.features.build import Matrices, build_panel
from floatwise.schemas import IntegrationEvent

if TYPE_CHECKING:
    from floatwise.api.store import Store


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def day_of(event: dict) -> str:
    return (
        dt.datetime.fromisoformat(event["occurred_at"])
        .astimezone(dt.timezone(dt.timedelta(hours=6)))
        .date()
        .isoformat()
    )


class Integration:
    def __init__(self, store: Store):
        self.store = store
        self.db = store.operations
        self.cfg = store.cfg.integration
        self.policy_version = hashlib.sha256(encode(store.cfg.policy.model_dump()).encode()).hexdigest()[:16]
        with self.db.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS integration_events (
                    id INTEGER PRIMARY KEY, source TEXT NOT NULL, event_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL, kind TEXT NOT NULL, occurred_at TEXT NOT NULL,
                    received_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0, error TEXT, processed_at TEXT,
                    next_attempt REAL NOT NULL DEFAULT 0, payload TEXT NOT NULL,
                    UNIQUE(source, event_id));
                CREATE INDEX IF NOT EXISTS integration_pending ON integration_events(status, id);
                CREATE TABLE IF NOT EXISTS integration_days (
                    agent_id TEXT NOT NULL, day TEXT NOT NULL,
                    cashin INTEGER NOT NULL DEFAULT 0, cashout INTEGER NOT NULL DEFAULT 0,
                    denied_cashin INTEGER NOT NULL DEFAULT 0, denied_cashout INTEGER NOT NULL DEFAULT 0,
                    closed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(agent_id, day));
                CREATE TABLE IF NOT EXISTS integration_revisions (
                    agent_id TEXT PRIMARY KEY, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS integration_snapshots (
                    source TEXT NOT NULL, agent_id TEXT NOT NULL, day TEXT NOT NULL,
                    sequence INTEGER NOT NULL, PRIMARY KEY(source, agent_id, day));
                CREATE TABLE IF NOT EXISTS integration_forecasts (
                    agent_id TEXT NOT NULL, day TEXT NOT NULL, revision INTEGER NOT NULL,
                    model_version TEXT NOT NULL, policy_version TEXT NOT NULL,
                    generated_at TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(agent_id, day));
                CREATE TABLE IF NOT EXISTS integration_control (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS integration_tasks (
                    id INTEGER PRIMARY KEY, decision_id INTEGER UNIQUE NOT NULL,
                    agent_id TEXT NOT NULL, day TEXT NOT NULL, status TEXT NOT NULL,
                    version INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS integration_models (
                    version TEXT PRIMARY KEY, directory TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS integration_inference (
                    id INTEGER PRIMARY KEY, at TEXT NOT NULL, latency_ms REAL NOT NULL,
                    success INTEGER NOT NULL);
            """)
        self._register_initial_model()

    @staticmethod
    def control(db, key: str, default=None):
        row = db.execute("SELECT value FROM integration_control WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def set_control(db, key: str, value) -> None:
        db.execute(
            "INSERT INTO integration_control VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, encode(value)),
        )

    @staticmethod
    def revision(db, agent: str) -> int:
        row = db.execute("SELECT revision FROM integration_revisions WHERE agent_id=?", (agent,)).fetchone()
        return row[0] if row else 0

    def _register_initial_model(self) -> None:
        from floatwise.integration.registry import register_model

        register_model(self.store.cfg, self.db, self.store.cfg.models_dir, self.store.metrics)
        with self.db.transaction() as db:
            if self.control(db, "active_model") is None:
                self.set_control(db, "active_model", self.store.models.version)

    def sync_model(self) -> None:
        from pathlib import Path

        from floatwise.models.predict import QuantileModels

        with self.db.connect() as db:
            active = self.control(db, "active_model")
            row = db.execute("SELECT directory FROM integration_models WHERE version=?", (active,)).fetchone()
        if active != self.store.models.version:
            if row is None:
                raise Conflict("The active model is not registered")
            loaded = QuantileModels.load(self.store.cfg, Path(row[0]))
            if (
                loaded.features != self.store.models.features
                or loaded.quantiles != self.store.cfg.model.quantiles
                or loaded.targets != self.store.cfg.model.targets
            ):
                raise Conflict("Active model feature schema is incompatible")
            self.store.models = loaded
            self.store._network_rec.cache_clear()
            self.store._panel_at.cache_clear()

    def submit(self, event: IntegrationEvent, actor: str) -> dict:
        body = event.model_dump(mode="json")
        agent, day = body["agent_id"], dt.date.fromisoformat(day_of(body))
        self.store.agent_index(agent)
        self.store.check_date(day)
        payload = body["payload"]
        if body["source"] == "simulated-dso" and payload["kind"] != "delivery_confirmation":
            raise Conflict("DSO source only accepts delivery confirmations")
        if body["source"] == "simulated-upstream" and payload["kind"] == "delivery_confirmation":
            raise Conflict("Delivery confirmations require the DSO source")
        if payload["kind"] == "transaction" and (
            (payload["outcome"] == "denied") != (payload["failure_code"] is not None)
        ):
            raise Conflict("Denied transactions require a failure code; served transactions cannot have one")
        if payload["kind"] in {"balance_snapshot", "delivery_confirmation"}:
            capacity = int(self.store.capacity[self.store.agent_index(agent)])
            if payload["cash"] + payload["efloat"] != capacity:
                raise Conflict("The simulated balance must conserve the agent's float capacity")
        if event.occurred_at > dt.datetime.now(dt.UTC):
            raise Conflict("Future event timestamps are not accepted")
        with self.db.transaction() as db:
            row = db.execute(
                "SELECT id,payload FROM integration_events WHERE source=? AND event_id=?",
                (body["source"], body["event_id"]),
            ).fetchone()
            if row:
                if json.loads(row[1]) != body:
                    raise Conflict("Event ID was already used with a different payload")
                return self.receipt(db, row[0], True)
            cur = db.execute(
                """INSERT INTO integration_events
                (source,event_id,agent_id,kind,occurred_at,received_at,payload) VALUES (?,?,?,?,?,?,?)""",
                (
                    body["source"],
                    body["event_id"],
                    agent,
                    payload["kind"],
                    body["occurred_at"],
                    now(),
                    encode(body),
                ),
            )
            self.db._audit(
                db, actor, "event_received", agent, {"event_id": body["event_id"], "kind": payload["kind"]}
            )
            return self.receipt(db, cur.lastrowid)

    @staticmethod
    def receipt(db, event_id: int, duplicate: bool = False) -> dict:
        fields = (
            "id",
            "source",
            "event_id",
            "agent_id",
            "kind",
            "occurred_at",
            "received_at",
            "status",
            "attempts",
            "error",
            "processed_at",
        )
        row = db.execute(
            f"SELECT {','.join(fields)} FROM integration_events WHERE id=?", (event_id,)
        ).fetchone()
        if row is None:
            raise Conflict("Unknown event receipt")
        return {**dict(zip(fields, row, strict=True)), "duplicate": duplicate}

    def retry(self, receipt_id: int, actor: str) -> dict:
        with self.db.transaction() as db:
            result = self.receipt(db, receipt_id)
            if result["status"] != "failed":
                raise Conflict("Only failed events can be retried")
            db.execute(
                "UPDATE integration_events SET status='pending',attempts=0,error=NULL,next_attempt=0 WHERE id=?",
                (receipt_id,),
            )
            self.db._audit(db, actor, "event_retry_requested", str(receipt_id), {})
            return self.receipt(db, receipt_id)

    def process_one(self) -> bool:
        """BEGIN IMMEDIATE serializes consumers; projection and acknowledgement commit together."""
        with self.db.transaction() as db:
            row = db.execute("""SELECT id,payload,attempts FROM integration_events
                WHERE status='pending' ORDER BY id LIMIT 1""").fetchone()
            if row is None:
                return False
            waiting = db.execute(
                "SELECT next_attempt FROM integration_events WHERE id=?", (row[0],)
            ).fetchone()[0]
            if waiting > time.time():
                return False  # preserve order while retrying
            event_id, encoded, attempts = row
            body = json.loads(encoded)
            db.execute("SAVEPOINT project")
            try:
                self._project(db, body)
                db.execute("RELEASE project")
                db.execute(
                    "UPDATE integration_events SET status='processed',attempts=?,error=NULL,processed_at=? WHERE id=?",
                    (attempts + 1, now(), event_id),
                )
                self.db._audit(
                    db,
                    "integration-worker",
                    "event_processed",
                    body["agent_id"],
                    {"receipt_id": event_id, "kind": body["payload"]["kind"]},
                )
            except (Conflict, ValueError) as exc:
                db.execute("ROLLBACK TO project")
                db.execute("RELEASE project")
                attempts += 1
                db.execute(
                    "UPDATE integration_events SET status=?,attempts=?,error=?,next_attempt=? WHERE id=?",
                    (
                        "failed" if attempts >= self.cfg.max_attempts else "pending",
                        attempts,
                        str(exc),
                        time.time() + self.cfg.retry_seconds,
                        event_id,
                    ),
                )
                self.db._audit(
                    db,
                    "integration-worker",
                    "event_processing_failed",
                    body["agent_id"],
                    {"receipt_id": event_id, "reason": str(exc)},
                )
        return True

    def _project(self, db, body: dict) -> None:
        agent, day, payload = body["agent_id"], day_of(body), body["payload"]
        kind = payload["kind"]
        if kind == "delivery_confirmation":
            self._complete(db, body)
        elif kind == "balance_snapshot":
            previous = db.execute(
                "SELECT sequence FROM integration_snapshots WHERE source=? AND agent_id=? AND day=?",
                (body["source"], agent, day),
            ).fetchone()
            if previous and payload["sequence"] <= previous[0]:
                raise Conflict("Balance snapshot sequence must increase")
            db.execute(
                "INSERT INTO integration_snapshots VALUES (?,?,?,?) ON CONFLICT(source,agent_id,day) DO UPDATE SET sequence=excluded.sequence",
                (body["source"], agent, day, payload["sequence"]),
            )
            self._set_balance(db, agent, day, payload["cash"], payload["efloat"])
        else:
            db.execute("INSERT OR IGNORE INTO integration_days(agent_id,day) VALUES (?,?)", (agent, day))
            if kind == "day_closed":
                snapshot = db.execute(
                    "SELECT 1 FROM balances WHERE agent_id=? AND day=?", (agent, day)
                ).fetchone()
                if not snapshot:
                    raise Conflict("A balance snapshot is required before closing the day")
                db.execute("UPDATE integration_days SET closed=1 WHERE agent_id=? AND day=?", (agent, day))
            elif kind == "transaction":
                column = payload["side"] if payload["outcome"] == "served" else f"denied_{payload['side']}"
                delta = (
                    payload["amount"]
                    if payload["outcome"] == "served"
                    else int(payload["failure_code"] == "liquidity")
                )
                db.execute(
                    f"UPDATE integration_days SET {column}={column}+?,closed=0 WHERE agent_id=? AND day=?",
                    (delta, agent, day),
                )
        self.bump(db, agent)

    @staticmethod
    def bump(db, agent: str) -> None:
        db.execute(
            "INSERT INTO integration_revisions VALUES (?,1) ON CONFLICT(agent_id) DO UPDATE SET revision=revision+1",
            (agent,),
        )

    @staticmethod
    def _set_balance(db, agent: str, day: str, cash: int, efloat: int) -> None:
        db.execute(
            "INSERT INTO balances VALUES (?,?,1,?,?) ON CONFLICT(agent_id,day) DO UPDATE SET version=version+1,cash=excluded.cash,efloat=excluded.efloat",
            (agent, day, cash, efloat),
        )

    def rows(self, agent: str, day: dt.date) -> tuple[int, list]:
        with self.db.connect() as db:
            db.execute("BEGIN")
            revision = self.revision(db, agent)
            rows = db.execute(
                "SELECT day,cashin,cashout,denied_cashin,denied_cashout,closed FROM integration_days WHERE agent_id=? AND day<=? ORDER BY day",
                (agent, str(day)),
            ).fetchall()
        return revision, rows

    def matrix(self, agent: str, day: dt.date) -> tuple[int, Matrices]:
        revision, rows = self.rows(agent, day)
        if any(not row[5] for row in rows):
            raise Conflict(
                "Transaction history is open; close the affected day before forecasting or approval"
            )
        i = self.store.agent_index(agent)
        base = self.store.m
        m = Matrices(
            np.array([agent]),
            base.dates,
            {s: a[i : i + 1].copy() for s, a in base.y.items()},
            {s: a[i : i + 1].copy() for s, a in base.demand.items()},
            {s: a[i : i + 1].copy() for s, a in base.stockout.items()},
        )
        for date, ci, co, di, do, _ in rows:
            t = self.store.date_pos[dt.date.fromisoformat(date)]
            m.y["cashin"][0, t], m.y["cashout"][0, t] = ci, co
            m.stockout["cashin"][0, t], m.stockout["cashout"][0, t] = bool(di), bool(do)
        return revision, m

    def infer(self, agent: str, day: dt.date) -> dict:
        self.sync_model()
        revision, m = self.matrix(agent, day)
        model = self.store.models
        with self.db.connect() as db:
            row = db.execute(
                "SELECT payload FROM integration_forecasts WHERE agent_id=? AND day=? AND revision=? AND model_version=? AND policy_version=?",
                (agent, str(day), revision, model.version, self.policy_version),
            ).fetchone()
        if row:
            result = json.loads(row[0])
            result["balance_revision"] = self.store.balance(agent, day)["version"]
            return result
        started = time.perf_counter()
        try:
            panel = build_panel(
                self.store.cfg,
                m,
                self.store.calendar,
                self.store.agents,
                np.array([self.store.date_pos[day]]),
            )
            predictions = {s: model.predict_amount(panel, s) for s in model.targets}
            points = [
                {
                    "date": str(day + dt.timedelta(days=h + 1)),
                    "horizon": h + 1,
                    **{
                        s: dict(
                            zip(
                                ("p10", "p50", "p90"),
                                np.round(predictions[s][h]).astype(int).tolist(),
                                strict=True,
                            )
                        )
                        for s in ("cashout", "cashin")
                    },
                }
                for h in range(self.store.cfg.model.horizons)
            ]
            result = {
                "agent_id": agent,
                "origin": str(day),
                "points": points,
                "source": "live",
                "model_version": model.version,
                "history_revision": revision,
                "policy_version": self.policy_version,
                "balance_revision": self.store.balance(agent, day)["version"],
            }
            with self.db.transaction() as db:
                if self.revision(db, agent) != revision or self.control(db, "active_model") != model.version:
                    raise Conflict("Operational inputs changed during inference; retry with current history")
                db.execute(
                    "INSERT INTO integration_forecasts VALUES (?,?,?,?,?,?,?) ON CONFLICT(agent_id,day) DO UPDATE SET revision=excluded.revision,model_version=excluded.model_version,policy_version=excluded.policy_version,generated_at=excluded.generated_at,payload=excluded.payload",
                    (agent, str(day), revision, model.version, self.policy_version, now(), encode(result)),
                )
                db.execute(
                    "INSERT INTO integration_inference(at,latency_ms,success) VALUES (?,?,1)",
                    (now(), (time.perf_counter() - started) * 1000),
                )
            return result
        except Exception:
            with self.db.transaction() as db:
                db.execute(
                    "INSERT INTO integration_inference(at,latency_ms,success) VALUES (?,?,0)",
                    (now(), (time.perf_counter() - started) * 1000),
                )
            raise

    def overrides(self, day: dt.date) -> dict[str, dict]:
        self.sync_model()
        with self.db.connect() as db:
            agents = [r[0] for r in db.execute("SELECT agent_id FROM integration_revisions")]
        return {agent: self.infer(agent, day) for agent in agents}

    def refresh_dirty(self) -> None:
        with self.db.connect() as db:
            rows = db.execute(
                "SELECT agent_id,MAX(day) FROM integration_days GROUP BY agent_id HAVING MIN(closed)=1"
            ).fetchall()
        for agent, day in rows:
            self.infer(agent, dt.date.fromisoformat(day))

    def connector(self, body: dict, actor: str) -> dict:
        agent, day = body["agent_id"], body["date"]
        self.store.agent_index(agent)
        self.store.check_date(day)
        with self.db.transaction() as db:
            state = self.control(db, "connector", {"status": "idle"})
            if body["action"] in {"pause", "resume", "replay"}:
                if not state.get("run_id") or state["agent_id"] != agent or state["date"] != str(day):
                    raise Conflict("Select the existing connector's agent and date")
                state["status"] = "paused" if body["action"] == "pause" else "running"
                state["error"] = None
                if body["action"] == "replay":
                    state["cursor"] = 0  # reuse IDs: replay proves deduplication
            else:
                if state.get("status") in {"running", "paused"}:
                    raise Conflict("A connector run is already active")
                existing = db.execute(
                    "SELECT 1 FROM integration_days WHERE agent_id=? AND day=?", (agent, str(day))
                ).fetchone()
                if existing:
                    raise Conflict(
                        "This date already has replay history; use Replay or select another agent/date"
                    )
                state = {
                    "run_id": uuid.uuid4().hex,
                    "agent_id": agent,
                    "date": str(day),
                    "status": "running",
                    "cursor": 0,
                    "total": self.cfg.connector_events + 3,
                    "error": None,
                }
            self.set_control(db, "connector", state)
            self.db._audit(db, actor, "connector_" + body["action"], agent, state)
        return state

    def connector_event(self, state: dict) -> IntegrationEvent:
        day = dt.date.fromisoformat(state["date"])
        i = self.store.agent_index(state["agent_id"])
        t, cursor = self.store.date_pos[day], state["cursor"]
        count = self.cfg.connector_events
        if cursor < count:
            side = "cashout" if cursor % 2 == 0 else "cashin"
            n = (count + 1) // 2 if side == "cashout" else count // 2
            amount = int(self.store.m.y[side][i, t] / max(1, n))
            if side == "cashout":
                amount = int(amount * self.cfg.connector_cashout_multiplier)
            payload = {"kind": "transaction", "side": side, "outcome": "served", "amount": max(1, amount)}
        elif cursor == count:
            payload = {
                "kind": "transaction",
                "side": "cashout",
                "outcome": "denied",
                "failure_code": "liquidity",
                "amount": self.cfg.connector_denied_amount,
            }
        elif cursor == count + 1:
            payload = {
                "kind": "balance_snapshot",
                "cash": 0,
                "efloat": int(self.store.capacity[i]),
                "sequence": 1,
            }
        else:
            payload = {"kind": "day_closed"}
        timestamp = dt.datetime.combine(day, dt.time(12), tzinfo=dt.timezone(dt.timedelta(hours=6)))
        timestamp += dt.timedelta(seconds=cursor)
        return IntegrationEvent(
            source="simulated-upstream",
            event_id=f"{state['run_id']}:{cursor}",
            agent_id=state["agent_id"],
            occurred_at=timestamp,
            payload=payload,
        )

    def _check_task_current(self, db, task: dict, completing: bool = False) -> None:
        if db.execute(
            "SELECT 1 FROM integration_events WHERE agent_id=? AND status='pending' AND (?=0 OR kind<>'delivery_confirmation') LIMIT 1",
            (task["agent_id"], int(completing)),
        ).fetchone():
            raise Conflict("Operational events are pending; wait for processing before dispatch or delivery")
        version = db.execute(
            "SELECT version FROM balances WHERE agent_id=? AND day=?", (task["agent_id"], task["date"])
        ).fetchone()
        if (
            self.revision(db, task["agent_id"]) != task["history_revision"]
            or (version[0] if version else 0) != task["balance_revision"]
            or self.control(db, "active_model") != task["model_version"]
            or self.policy_version != task["policy_version"]
        ):
            raise Conflict("Task inputs changed; cancel this task and approve a fresh recommendation")
        if db.execute(
            "SELECT 1 FROM integration_days WHERE agent_id=? AND day<=? AND closed=0",
            (task["agent_id"], task["date"]),
        ).fetchone():
            raise Conflict("Task history is open; recalculation and a fresh approval are required")

    def create_task(self, decision_id: int, actor: str) -> dict:
        with self.db.transaction() as db:
            existing = db.execute(
                "SELECT payload FROM integration_tasks WHERE decision_id=?", (decision_id,)
            ).fetchone()
            if existing:
                return json.loads(existing[0])
            row = db.execute("SELECT payload FROM decisions WHERE id=?", (decision_id,)).fetchone()
            if not row:
                raise Conflict("Unknown decision")
            decision = json.loads(row[0])
            if decision["decision"] not in {"approve", "modify"} or decision["final_amount"] <= 0:
                raise Conflict("A task requires an approved non-zero operation")
            if decision["action"] not in {"TOP_UP_CASH", "TOP_UP_EFLOAT"}:
                raise Conflict(
                    "Extra float requires separate human escalation; the simulated adapter only handles exchanges"
                )
            if any(
                decision.get(k) is None
                for k in ("history_revision", "model_version", "policy_version", "balance_version")
            ):
                raise Conflict("Approve a fresh recommendation with integration provenance")
            if db.execute(
                "SELECT 1 FROM integration_tasks WHERE agent_id=? AND day=? AND status NOT IN ('completed','cancelled','rejected')",
                (decision["agent_id"], decision["date"]),
            ).fetchone():
                raise Conflict("An active DSO task already exists for this agent and date")
            agent = self.store.agents.iloc[self.store.agent_index(decision["agent_id"])]
            task = {
                "decision_id": decision_id,
                "agent_id": decision["agent_id"],
                "dso_id": str(agent["dso_id"]),
                "date": decision["date"],
                "action": decision["action"],
                "amount": decision["final_amount"],
                "status": "approved",
                "version": 1,
                "history_revision": decision["history_revision"],
                "balance_revision": decision["balance_version"],
                "model_version": decision["model_version"],
                "policy_version": decision["policy_version"],
                "delivery_reference": None,
                "created_at": now(),
                "updated_at": now(),
            }
            self._check_task_current(db, task)
            cur = db.execute(
                "INSERT INTO integration_tasks(decision_id,agent_id,day,status,version,payload) VALUES (?,?,?,?,?,?)",
                (decision_id, task["agent_id"], task["date"], "approved", 1, "{}"),
            )
            task["id"] = cur.lastrowid
            self._save_task(db, task, actor)
            return task

    def task(self, db, task_id: int) -> dict:
        row = db.execute("SELECT payload FROM integration_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise Conflict("Unknown DSO task")
        return json.loads(row[0])

    def _save_task(self, db, task: dict, actor: str) -> None:
        db.execute(
            "UPDATE integration_tasks SET status=?,version=?,payload=? WHERE id=?",
            (task["status"], task["version"], encode(task), task["id"]),
        )
        self.db._audit(db, actor, "dso_task_" + task["status"], str(task["id"]), task)

    def transition(self, task_id: int, status: str, version: int, actor: str) -> dict:
        allowed = {
            "approved": {"dispatched", "cancelled"},
            "dispatched": {"accepted", "rejected", "cancelled"},
            "accepted": {"cancelled"},
        }
        with self.db.transaction() as db:
            task = self.task(db, task_id)
            if version != task["version"]:
                raise Conflict("DSO task changed; reload its current version")
            if status not in allowed.get(task["status"], set()):
                raise Conflict("Invalid DSO task transition")
            if status not in {"cancelled", "rejected"}:
                self._check_task_current(db, task)
            if status == "dispatched":
                assigned = [
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT payload FROM integration_tasks WHERE day=? AND status IN ('dispatched','accepted','completed')",
                        (task["date"],),
                    )
                ]
                assigned = [item for item in assigned if item["dso_id"] == task["dso_id"]]
                policy = self.store.cfg.policy.dso
                cash = sum(item["amount"] for item in assigned if item["action"] == "TOP_UP_CASH")
                cash += task["amount"] if task["action"] == "TOP_UP_CASH" else 0
                if len(assigned) >= policy.max_visits or cash > policy.max_cash:
                    raise Conflict("Dispatch exceeds the DSO's configured daily visit or cash-bag limit")
            task.update(status=status, version=version + 1, updated_at=now())
            self._save_task(db, task, actor)
            return task

    def delivery_event(self, task_id: int, version: int) -> IntegrationEvent:
        with self.db.connect() as db:
            task = self.task(db, task_id)
            if task["version"] != version or task["status"] != "accepted":
                raise Conflict("Delivery requires a current accepted task")
            self._check_task_current(db, task)
        balance = self.store.balance(task["agent_id"], dt.date.fromisoformat(task["date"]))
        delta = task["amount"] if task["action"] == "TOP_UP_CASH" else -task["amount"]
        cash, efloat = balance["cash"] + delta, balance["efloat"] - delta
        if min(cash, efloat) < 0:
            raise Conflict("The approved exchange exceeds the available opposite balance")
        stamp = dt.datetime.combine(
            dt.date.fromisoformat(task["date"]), dt.time(18), tzinfo=dt.timezone(dt.timedelta(hours=6))
        )
        return IntegrationEvent(
            source="simulated-dso",
            event_id=f"delivery:{task_id}:{version}",
            agent_id=task["agent_id"],
            occurred_at=stamp,
            payload={
                "kind": "delivery_confirmation",
                "task_id": task_id,
                "reference": f"SIM-DSO-{task_id}",
                "cash": cash,
                "efloat": efloat,
            },
        )

    def _complete(self, db, body: dict) -> None:
        payload = body["payload"]
        task = self.task(db, payload["task_id"])
        if (
            task["status"] != "accepted"
            or task["agent_id"] != body["agent_id"]
            or task["date"] != day_of(body)
        ):
            raise Conflict("Delivery does not match an accepted task")
        self._check_task_current(db, task, completing=True)
        balance = db.execute(
            "SELECT cash,efloat FROM balances WHERE agent_id=? AND day=?", (task["agent_id"], task["date"])
        ).fetchone()
        if not balance:
            balance = (
                int(
                    self.store.close_cash[
                        self.store.agent_index(task["agent_id"]),
                        self.store.date_pos[dt.date.fromisoformat(task["date"])],
                    ]
                ),
                int(
                    self.store.close_efloat[
                        self.store.agent_index(task["agent_id"]),
                        self.store.date_pos[dt.date.fromisoformat(task["date"])],
                    ]
                ),
            )
        delta = task["amount"] if task["action"] == "TOP_UP_CASH" else -task["amount"]
        if (payload["cash"], payload["efloat"]) != (balance[0] + delta, balance[1] - delta):
            raise Conflict("Delivery balance does not reconcile with the approved exchange")
        self._set_balance(db, task["agent_id"], task["date"], payload["cash"], payload["efloat"])
        task.update(
            status="completed",
            version=task["version"] + 1,
            delivery_reference=payload["reference"],
            updated_at=now(),
        )
        self._save_task(db, task, "simulated-dso")

    def status(self) -> dict:
        self.sync_model()
        with self.db.connect() as db:
            db.execute("BEGIN")
            connector = self.control(db, "connector", {"status": "idle"})
            heartbeat = self.control(db, "worker_heartbeat")
            counts = dict(db.execute("SELECT status,COUNT(*) FROM integration_events GROUP BY status"))
            retries = db.execute(
                "SELECT COALESCE(SUM(MAX(attempts-1,0)),0) FROM integration_events"
            ).fetchone()[0]
            pending = db.execute(
                "SELECT MIN(received_at) FROM integration_events WHERE status='pending'"
            ).fetchone()[0]
            lag = (
                max(0, (dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(pending)).total_seconds())
                if pending
                else 0
            )
            delays = [
                max(0, (dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)).total_seconds())
                for a, b in db.execute(
                    "SELECT received_at,processed_at FROM integration_events WHERE status='processed'"
                )
            ]
            latencies = [
                r[0]
                for r in db.execute(
                    "SELECT latency_ms FROM integration_inference WHERE success=1 ORDER BY id DESC LIMIT 1000"
                )
            ]
            inference_count = db.execute(
                "SELECT COUNT(*) FROM integration_inference WHERE success=1"
            ).fetchone()[0]
            errors = db.execute("SELECT COUNT(*) FROM integration_inference WHERE success=0").fetchone()[0]
            stale = db.execute(
                """SELECT COUNT(*) FROM integration_forecasts f JOIN integration_revisions r USING(agent_id)
                WHERE f.revision<>r.revision OR f.model_version<>? OR f.generated_at<?""",
                (
                    self.store.models.version,
                    (dt.datetime.now(dt.UTC) - dt.timedelta(seconds=self.cfg.stale_seconds)).isoformat(),
                ),
            ).fetchone()[0]
            failures = db.execute(
                "SELECT COUNT(*) FROM integration_events WHERE kind='delivery_confirmation' AND error IS NOT NULL"
            ).fetchone()[0]
            events = [
                self.receipt(db, row[0])
                for row in db.execute("SELECT id FROM integration_events ORDER BY id DESC LIMIT 50")
            ]
            tasks = [
                json.loads(r[0])
                for r in db.execute("SELECT payload FROM integration_tasks ORDER BY id DESC LIMIT 50")
            ]
            models = [
                json.loads(r[0])
                for r in db.execute("SELECT payload FROM integration_models ORDER BY version")
            ]
            daily = db.execute(
                "SELECT agent_id,day,cashin,cashout FROM integration_days WHERE closed=1"
            ).fetchall()
        ratios = {side: [] for side in ("cashin", "cashout")}
        for agent, date, ci, co in daily:
            i, t = self.store.agent_index(agent), self.store.date_pos[dt.date.fromisoformat(date)]
            for side, value in (("cashin", ci), ("cashout", co)):
                baseline = max(1000, float(self.store.m.y[side][i, max(0, t - 28) : t].mean()))
                ratios[side].append(value / baseline)
        # Synthetic training reference, normalised by each agent's prior 28 served days.
        changes = {}
        for side in ratios:
            reference = self.store.training_reference[side]
            changes[side] = float(np.mean(ratios[side]) / max(reference, 0.001) - 1) if daily else None
        enough = len(daily) >= self.cfg.drift_min_samples
        review = enough and any(abs(v) >= self.cfg.drift_mean_ratio for v in changes.values())
        return {
            "simulated": True,
            "connector": connector,
            "worker": {
                "heartbeat_at": heartbeat,
                "online": bool(
                    heartbeat
                    and (dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(heartbeat)).total_seconds()
                    < self.cfg.stale_seconds
                ),
                "connector_configured": bool(os.environ.get("FLOATWISE_INTEGRATION_TOKEN")),
            },
            "metrics": {
                "queue_depth": counts.get("pending", 0),
                "processed": counts.get("processed", 0),
                "failed": counts.get("failed", 0),
                "retries": retries,
                "oldest_pending_seconds": round(lag, 2),
                "average_processing_seconds": round(float(np.mean(delays)), 3) if delays else 0,
                "inference_count": inference_count,
                "inference_errors": errors,
                "inference_p95_ms": round(float(np.quantile(latencies, 0.95)), 2) if latencies else 0,
                "reconciliation_failures": failures,
                "stale_forecasts": stale,
            },
            "drift": {
                "status": "review_required"
                if review
                else "within_reference"
                if enough
                else "insufficient_data",
                "sample_count": len(daily),
                "minimum_samples": self.cfg.drift_min_samples,
                "threshold": self.cfg.drift_mean_ratio,
                **{f"{side}_mean_ratio_change": value for side, value in changes.items()},
                "note": "Completed replay days versus synthetic training reference; a review signal, not validated production drift.",
            },
            "active_model": self.store.models.version,
            "models": models,
            "events": events,
            "tasks": tasks,
        }
