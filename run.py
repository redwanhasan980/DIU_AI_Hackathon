#!/usr/bin/env python3
"""Cross-platform launcher for FloatWise (works on Windows, macOS and Linux; no `make` needed).

    python run.py setup     # create .venv, install Python + web dependencies      (~2 min)
    python run.py all       # generate data, train, evaluate, backtest, plots       (~3 min)
    python run.py demo      # build the web app and serve everything on http://localhost:8000
    python run.py test      # backend test suite
    python run.py dev       # API with auto-reload on :8000 + web dev server on :5173
    python run.py validate  # held-out calibration, ablations and sensitivity experiments
    python run.py benchmark # replicated inference and planning scale benchmark
    python run.py fixtures  # refresh offline read fixtures
    python run.py auth-setup # configure local viewer/operator/admin password accounts
    python run.py integration-setup # configure a local connector service credential
    python run.py integration-worker # run the durable event consumer separately
    python run.py integration-benchmark # benchmark the complete local pipeline
    python run.py models list # model registry; retrain, register, activate, rollback

Needs Python 3.11+ and Node.js 20+ on PATH. Same steps as the Makefile targets.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
NPM = shutil.which("npm") or "npm"


def sh(cmd: list[str], cwd: Path = ROOT, env: dict | None = None) -> None:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    result = subprocess.run(
        [str(c) for c in cmd], cwd=cwd, env={**os.environ, **(env or {})}, check=False
    )
    if result.returncode != 0:
        sys.exit(result.returncode)


def need_venv() -> None:
    if not PY.exists():
        sys.exit("Python environment missing — run `python run.py setup` first.")


def setup() -> None:
    if sys.version_info < (3, 11):
        sys.exit(f"Python 3.11+ is required (found {sys.version.split()[0]}).")
    if not shutil.which("npm"):
        sys.exit("Node.js 20+ (with npm) is required: https://nodejs.org/")
    if not PY.exists():
        print("creating .venv …")
        venv.create(VENV, with_pip=True)
    sh([PY, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    sh([PY, "-m", "pip", "install", "-q", "-e", f"{BACKEND}[dev]"])
    sh([NPM, "ci"], cwd=FRONTEND)
    print("\nsetup done — next: python run.py all")


def pipeline() -> None:
    need_venv()
    for module in ("floatwise.data.generate", "floatwise.models.train", "floatwise.models.evaluate",
                   "floatwise.simulation.backtest"):  # fmt: skip
        sh([PY, "-m", module], cwd=BACKEND)
    sh([PY, "scripts/plot_data_checks.py"], cwd=BACKEND)
    sh([PY, "scripts/build_narratives.py"], cwd=BACKEND)
    print("\npipeline done — next: python run.py demo")


def demo() -> None:
    need_venv()
    integration_setup(quiet=True)
    if not (ROOT / "artifacts" / "forecasts.parquet").exists():
        print("artifacts missing — running the pipeline first")
        pipeline()
    sh([NPM, "run", "build"], cwd=FRONTEND)
    print("\nFloatWise is starting on http://localhost:8000  (Ctrl+C to stop)\n")
    worker = subprocess.Popen([str(PY), "-m", "floatwise.integration.worker"], cwd=BACKEND)
    try:
        sh([PY, "-m", "uvicorn", "floatwise.api.main:app", "--port", "8000"], cwd=BACKEND,
           env={"FLOATWISE_SERVE_WEB": "1"})  # fmt: skip
    finally:
        worker.terminate()
        worker.wait()


def dev() -> None:
    need_venv()
    integration_setup(quiet=True)
    api = subprocess.Popen([str(PY), "-m", "uvicorn", "floatwise.api.main:app", "--reload", "--port", "8000"],
                           cwd=BACKEND)  # fmt: skip
    worker = subprocess.Popen([str(PY), "-m", "floatwise.integration.worker"], cwd=BACKEND)
    try:
        sh([NPM, "run", "dev"], cwd=FRONTEND)
    finally:
        api.terminate()
        worker.terminate()
        worker.wait()


def test() -> None:
    need_venv()
    sh([PY, "-m", "pytest"], cwd=BACKEND, env={"FLOATWISE_AUTH_MODE": "demo"})


def validation() -> None:
    need_venv()
    sh([PY, "scripts/judge_validation.py"], cwd=BACKEND)
    if (ROOT / "artifacts" / "scale_benchmark.json").exists():
        sh([PY, "scripts/summarize_validation.py"], cwd=BACKEND)


def benchmark() -> None:
    need_venv()
    sh([PY, "scripts/benchmark_scale.py"], cwd=BACKEND)
    if (ROOT / "artifacts" / "judge_validation.json").exists():
        sh([PY, "scripts/summarize_validation.py"], cwd=BACKEND)


def fixtures() -> None:
    need_venv()
    sh([PY, "scripts/export_fixtures.py"], cwd=BACKEND,
       env={"FLOATWISE_AUTH_MODE": "demo", "ANTHROPIC_API_KEY": ""})  # fmt: skip


def auth_setup() -> None:
    """Provision local password accounts; preserve existing hashes and unrelated secrets."""
    sys.path.insert(0, str(BACKEND))
    from floatwise.api.security import hash_password, valid_password_hash

    path = ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    existing = {}
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            existing[key.strip()] = value.strip()
    raw = existing.get("FLOATWISE_USERS", "")
    created = []
    if raw:
        try:
            records = json.loads(raw)
            usernames = set()
            if not isinstance(records, list) or not records:
                raise ValueError
            for record in records:
                username, role = record["username"], record["role"]
                if (
                    not isinstance(username, str)
                    or not username
                    or username != username.strip()
                    or len(username) > 64
                    or username in usernames
                    or role not in {"viewer", "operator", "admin"}
                    or not valid_password_hash(record["password_hash"])
                ):
                    raise ValueError
                usernames.add(username)
        except (ValueError, TypeError, KeyError):
            sys.exit("Existing FLOATWISE_USERS is invalid; no account was replaced.")
    else:
        records = []
        for role in ("viewer", "operator", "admin"):
            password = secrets.token_urlsafe(12)
            records.append(
                {
                    "username": role,
                    "role": role,
                    "password_hash": hash_password(password),
                }
            )
            created.append((role, password))
        raw = json.dumps(records, separators=(",", ":"))
    updates = {"FLOATWISE_AUTH_MODE": "required", "FLOATWISE_USERS": raw}
    # Migrate the earlier locally generated bearer accounts to password accounts.
    removed = {*updates, "FLOATWISE_CREDENTIALS"} if created else set(updates)
    kept = [
        line
        for line in lines
        if line.split("=", 1)[0].strip() not in removed
        and not line.startswith("# At /login, paste the token")
    ]
    if not lines:
        kept = [
            "# Local authentication configuration. Never commit this file.",
            "ANTHROPIC_API_KEY=",
            "LLM_MODEL=claude-opus-5-5",
            "",
        ]
    contents = (
        "\n".join([*kept, *(f"{key}={value}" for key, value in updates.items())]) + "\n"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(contents)
    if os.name != "nt":
        path.chmod(0o600)
    print(f"Password accounts configured in {path}")
    if created:
        print(
            "Local login credentials (shown once; passwords are stored only as hashes):"
        )
        for username, password in created:
            print(f"{username}: {password}")
    else:
        print("Existing accounts and passwords preserved.")
    print("Restart the API and sign in at /login with your username and password.")


def integration_setup(quiet: bool = False) -> None:
    """Generate a scoped connector secret without changing existing login accounts."""
    path = ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    value = next((line.split("=", 1)[1].strip() for line in lines
                  if line.startswith("FLOATWISE_INTEGRATION_TOKEN=")), "")
    if not value:
        lines = [line for line in lines if not line.startswith("FLOATWISE_INTEGRATION_TOKEN=")]
        lines.append("FLOATWISE_INTEGRATION_TOKEN=" + secrets.token_urlsafe(32))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if os.name != "nt":
            path.chmod(0o600)
    elif len(value) < 32:
        sys.exit("Existing FLOATWISE_INTEGRATION_TOKEN must contain at least 32 characters.")
    if not quiet:
        print("Connector service identity configured. Existing passwords preserved; secret not printed.")
        print("Restart API and worker. python run.py demo starts both processes.")


def integration_worker() -> None:
    need_venv()
    sh([PY, "-m", "floatwise.integration.worker"], cwd=BACKEND)


def integration_benchmark() -> None:
    need_venv()
    sh([PY, "scripts/benchmark_integration.py", *sys.argv[2:]], cwd=BACKEND)


def models() -> None:
    need_venv()
    sh([PY, "-m", "floatwise.integration.registry", *sys.argv[2:]], cwd=BACKEND)


COMMANDS = {
    "setup": setup,
    "all": pipeline,
    "demo": demo,
    "test": test,
    "dev": dev,
    "validate": validation,
    "benchmark": benchmark,
    "fixtures": fixtures,
    "auth-setup": auth_setup,
    "integration-setup": integration_setup,
    "integration-worker": integration_worker,
    "integration-benchmark": integration_benchmark,
    "models": models,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS or (len(sys.argv) > 2 and sys.argv[1] not in {"models", "integration-benchmark"}):
        print(__doc__)
        sys.exit(2)
    COMMANDS[sys.argv[1]]()
