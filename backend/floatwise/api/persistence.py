"""Transactional local operations storage. Each call owns its SQLite connection.

WAL permits concurrent readers; write transactions coordinate across API processes.
This is a prototype store; use PostgreSQL and an external audit sink for deployment.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Conflict(ValueError):
    pass


def encode(value: dict) -> str:
    return json.dumps(value, default=str, sort_keys=True, ensure_ascii=False)


def fingerprint(decision: dict) -> str:
    return hashlib.sha256(
        encode({k: v for k, v in decision.items() if k not in {"decided_at", "decision_id"}}).encode()
    ).hexdigest()


class OperationsDB:
    def __init__(self, path: Path, legacy: Path | None = None):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY, actor TEXT NOT NULL, idem TEXT,
                    fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(actor, idem));
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL,
                    event TEXT NOT NULL, resource TEXT NOT NULL, details TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS balances (
                    agent_id TEXT NOT NULL, day TEXT NOT NULL, version INTEGER NOT NULL,
                    cash INTEGER NOT NULL, efloat INTEGER NOT NULL,
                    PRIMARY KEY(agent_id, day));
                CREATE TABLE IF NOT EXISTS rate_limits (
                    principal TEXT NOT NULL, window INTEGER NOT NULL, count INTEGER NOT NULL,
                    PRIMARY KEY(principal, window));
                CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY, subject TEXT NOT NULL,
                    account_fingerprint TEXT NOT NULL, expires INTEGER NOT NULL);
            """)
        if legacy and legacy.exists():
            with self.transaction() as db:
                if not db.execute("SELECT 1 FROM migrations WHERE name='legacy_decisions'").fetchone():
                    for item in json.loads(legacy.read_text(encoding="utf-8")).get("decisions", []):
                        db.execute(
                            "INSERT INTO decisions(actor, fingerprint, payload) VALUES (?, ?, ?)",
                            ("legacy-demo", "legacy", encode(item)),
                        )
                    db.execute("INSERT INTO migrations VALUES ('legacy_decisions')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("PRAGMA busy_timeout=30000")
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def _audit(self, db, actor: str, event: str, resource: str, details: dict) -> None:
        db.execute(
            "INSERT INTO audit(at, actor, event, resource, details) VALUES (?, ?, ?, ?, ?)",
            (dt.datetime.now(dt.UTC).isoformat(), actor, event, resource, encode(details)),
        )

    def audit(self, actor: str, event: str, resource: str, details: dict) -> None:
        with self.transaction() as db:
            self._audit(db, actor, event, resource, details)

    def create_session(self, subject: str, account_fingerprint: str, ttl: int, previous: str = "") -> str:
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.transaction() as db:
            db.execute("DELETE FROM auth_sessions WHERE expires <= ?", (int(time.time()),))
            if previous:
                db.execute(
                    "DELETE FROM auth_sessions WHERE token_hash=?",
                    (hashlib.sha256(previous.encode()).hexdigest(),),
                )
            db.execute(
                "INSERT INTO auth_sessions VALUES (?, ?, ?, ?)",
                (digest, subject, account_fingerprint, int(time.time()) + ttl),
            )
            self._audit(db, subject, "login_succeeded", "session", {})
        return token

    def session_account(self, token: str) -> tuple[str, str] | None:
        if not token or len(token) > 128:
            return None
        with self.connect() as db:
            return db.execute(
                "SELECT subject, account_fingerprint FROM auth_sessions WHERE token_hash=? AND expires>?",
                (hashlib.sha256(token.encode()).hexdigest(), int(time.time())),
            ).fetchone()

    def revoke_session(self, token: str) -> None:
        with self.transaction() as db:
            digest = hashlib.sha256(token.encode()).hexdigest()
            row = db.execute("SELECT subject FROM auth_sessions WHERE token_hash=?", (digest,)).fetchone()
            db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest,))
            if row:
                self._audit(db, row[0], "logout", "session", {})

    def add_decision(self, decision: dict, actor: str, idem: str | None) -> dict:
        digest = fingerprint(decision)
        with self.transaction() as db:
            if idem:
                previous = db.execute(
                    "SELECT fingerprint, payload FROM decisions WHERE actor=? AND idem=?", (actor, idem)
                ).fetchone()
                if previous:
                    if previous[0] != digest:
                        raise Conflict("Idempotency-Key was already used for a different decision")
                    return json.loads(previous[1])
            expected = decision.get("balance_version")
            if expected is not None:
                row = db.execute(
                    "SELECT version FROM balances WHERE agent_id=? AND day=?",
                    (decision["agent_id"], str(decision["date"])),
                ).fetchone()
                if expected != (row[0] if row else 0):
                    raise Conflict("Balance changed; reload the recommendation before recording a decision")
            revision = decision.get("history_revision")
            if revision is not None:
                if db.execute(
                    "SELECT 1 FROM integration_events WHERE agent_id=? AND status='pending' LIMIT 1",
                    (decision["agent_id"],),
                ).fetchone():
                    raise Conflict("Wait for pending operational events before recording a decision")
                row = db.execute(
                    "SELECT revision FROM integration_revisions WHERE agent_id=?", (decision["agent_id"],)
                ).fetchone()
                active = db.execute(
                    "SELECT value FROM integration_control WHERE key='active_model'"
                ).fetchone()
                if (
                    revision != (row[0] if row else 0)
                    or not active
                    or json.loads(active[0]) != decision.get("model_version")
                ):
                    raise Conflict("History or model changed; reload the recommendation before approval")
                if db.execute(
                    "SELECT 1 FROM integration_days WHERE agent_id=? AND day<=? AND closed=0",
                    (decision["agent_id"], str(decision["date"])),
                ).fetchone():
                    raise Conflict("History is open; close the day and reload before approval")
            cur = db.execute(
                "INSERT INTO decisions(actor, idem, fingerprint, payload) VALUES (?, ?, ?, ?)",
                (actor, idem, digest, encode(decision)),
            )
            decision = {**decision, "decision_id": cur.lastrowid}
            db.execute("UPDATE decisions SET payload=? WHERE id=?", (encode(decision), cur.lastrowid))
            self._audit(db, actor, "decision_recorded", decision["agent_id"], decision)
        return decision

    def replay_decision(self, decision: dict, actor: str, idem: str | None) -> dict | None:
        if not idem:
            return None
        with self.connect() as db:
            row = db.execute(
                "SELECT fingerprint, payload FROM decisions WHERE actor=? AND idem=?", (actor, idem)
            ).fetchone()
        if not row:
            return None
        if row[0] != fingerprint(decision):
            raise Conflict("Idempotency-Key was already used for a different decision")
        return json.loads(row[1])

    def decisions(self) -> list[dict]:
        with self.connect() as db:
            return [
                {**json.loads(row[1]), "decision_id": row[0]}
                for row in db.execute("SELECT id,payload FROM decisions ORDER BY id")
            ]

    def audit_events(self, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, at, actor, event, resource, details FROM audit ORDER BY id DESC LIMIT ?", (limit,)
            )
            return [
                dict(
                    zip(
                        ("id", "at", "actor", "event", "resource", "details"),
                        (*row[:5], json.loads(row[5])),
                        strict=True,
                    )
                )
                for row in rows
            ]

    def allow_request(self, principal: str, window: int, limit: int) -> bool:
        with self.transaction() as db:
            db.execute("DELETE FROM rate_limits WHERE window < ?", (window,))
            db.execute(
                "INSERT INTO rate_limits VALUES (?, ?, 1) ON CONFLICT(principal, window) DO UPDATE SET count=count+1",
                (principal, window),
            )
            return (
                db.execute(
                    "SELECT count FROM rate_limits WHERE principal=? AND window=?", (principal, window)
                ).fetchone()[0]
                <= limit
            )

    def balance(self, agent_id: str, day: dt.date) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT version, cash, efloat FROM balances WHERE agent_id=? AND day=?", (agent_id, str(day))
            ).fetchone()
            return dict(zip(("version", "cash", "efloat"), row, strict=True)) if row else None

    def set_balance(
        self, agent_id: str, day: dt.date, cash: int, efloat: int, expected: int, actor: str
    ) -> dict:
        with self.transaction() as db:
            row = db.execute(
                "SELECT version FROM balances WHERE agent_id=? AND day=?", (agent_id, str(day))
            ).fetchone()
            version = row[0] if row else 0
            if version != expected:
                raise Conflict("Balance changed; reload the current version before retrying")
            db.execute(
                "INSERT INTO balances VALUES (?, ?, ?, ?, ?) ON CONFLICT(agent_id, day) DO UPDATE SET version=excluded.version, cash=excluded.cash, efloat=excluded.efloat",
                (agent_id, str(day), version + 1, cash, efloat),
            )
            self._audit(
                db,
                actor,
                "balance_observed",
                agent_id,
                {"day": str(day), "version": version + 1, "cash": cash, "efloat": efloat},
            )
        return {"version": version + 1, "cash": cash, "efloat": efloat}
