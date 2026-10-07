"""Explicit local demo mode or fail-closed bearer credentials with server-owned roles."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str


PASSWORD_ITERATIONS = 600_000
SESSION_COOKIE = "floatwise_session"


def hash_password(password: str) -> str:
    """Salted PBKDF2-HMAC-SHA256; passwords never enter the account configuration."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest.hex()}"


def valid_password_hash(value: str) -> bool:
    try:
        algorithm, iterations, salt, digest = value.split("$")
        return (
            algorithm == "pbkdf2_sha256"
            and int(iterations) == PASSWORD_ITERATIONS
            and len(bytes.fromhex(salt)) == 16
            and len(bytes.fromhex(digest)) == 32
        )
    except (ValueError, AttributeError):
        return False


def verify_password(password: str, encoded: str) -> bool:
    _, iterations, salt, expected = encoded.split("$")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return secrets.compare_digest(actual.hex(), expected)


class AccessControl:
    def __init__(self):
        self.mode = os.environ.get("FLOATWISE_AUTH_MODE", "demo")
        if self.mode not in {"demo", "required"}:
            raise ValueError("FLOATWISE_AUTH_MODE must be demo or required")
        self.credentials = []
        self.users: dict[str, tuple[str, Principal]] = {}
        self.dummy_hash = hash_password(secrets.token_urlsafe(32))
        if self.mode == "required":
            for item in json.loads(os.environ.get("FLOATWISE_USERS") or "[]"):
                username, role, encoded = item["username"], item["role"], item["password_hash"]
                if (
                    not isinstance(username, str)
                    or not username
                    or username != username.strip()
                    or len(username) > 64
                    or username in self.users
                    or role not in {"viewer", "operator", "admin"}
                    or not valid_password_hash(encoded)
                ):
                    raise ValueError("Users require unique usernames, valid roles and PBKDF2 password hashes")
                self.users[username] = (encoded, Principal(username, role))
            items = json.loads(os.environ.get("FLOATWISE_CREDENTIALS") or "[]")
            subjects, tokens = set(), set()
            for item in items:
                subject, role, token = item["subject"], item["role"], item["token"]
                if (
                    not subject
                    or subject in subjects
                    or role not in {"viewer", "operator", "admin"}
                    or len(token) < 32
                    or token in tokens
                ):
                    raise ValueError(
                        "Credentials require unique subjects, unique tokens of at least 32 characters, and valid roles"
                    )
                subjects.add(subject)
                tokens.add(token)
                self.credentials.append((hashlib.sha256(token.encode()).digest(), Principal(subject, role)))
            if not self.credentials and not self.users:
                raise ValueError(
                    "Required authentication needs FLOATWISE_USERS; run python run.py auth-setup"
                )

    def login(self, username: str, password: str) -> Principal | None:
        user = self.users.get(username)
        encoded = user[0] if user else self.dummy_hash
        matches = verify_password(password, encoded)
        return user[1] if user and matches else None

    def account_fingerprint(self, username: str) -> str:
        return hashlib.sha256(self.users[username][0].encode()).hexdigest()

    def session_principal(self, account: tuple[str, str] | None) -> Principal | None:
        if account is None or account[0] not in self.users:
            return None
        username, fingerprint = account
        return (
            self.users[username][1]
            if secrets.compare_digest(fingerprint, self.account_fingerprint(username))
            else None
        )

    def authenticate(self, authorization: str, host: str) -> Principal | None:
        if self.mode == "demo":
            try:
                local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = host == "testclient"  # Starlette's in-process test transport
            return Principal("local-demo", "admin") if local else None
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        digest = hashlib.sha256(token.encode()).digest()
        connector_token = os.environ.get("FLOATWISE_INTEGRATION_TOKEN", "")
        if len(connector_token) >= 32 and secrets.compare_digest(token, connector_token):
            return Principal("simulated-connector", "service")
        for expected, principal in self.credentials:
            if secrets.compare_digest(expected, digest):
                return principal
        return None

    @staticmethod
    def allowed(principal: Principal, method: str, path: str) -> bool:
        if principal.role == "service":
            return method == "POST" and path == "/api/v1/integration/events"
        if path.startswith("/api/v1/integration/"):
            if method == "GET":
                return True
            if path in {"/api/v1/integration/connector", "/api/v1/integration/events"} or "/retry" in path:
                return principal.role == "admin"
            return principal.role in {"operator", "admin"}
        if path.startswith("/api/v1/operations/"):
            return principal.role == "admin"
        if method == "GET":
            return True
        return principal.role in {"operator", "admin"} and path in {"/api/v1/decisions", "/api/v1/simulate"}
