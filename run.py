#!/usr/bin/env python3
"""Cross-platform launcher for FloatWise (works on Windows, macOS and Linux; no `make` needed).

    python run.py setup     # create .venv, install Python + web dependencies      (~2 min)
    python run.py all       # generate data, train, evaluate, backtest, plots       (~3 min)
    python run.py demo      # build the web app and serve everything on http://localhost:8000
    python run.py test      # backend test suite
    python run.py dev       # API with auto-reload on :8000 + web dev server on :5173

Needs Python 3.11+ and Node.js 20+ on PATH. Same steps as the Makefile targets.
"""

from __future__ import annotations

import os
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
    if not (ROOT / "artifacts" / "forecasts.parquet").exists():
        print("artifacts missing — running the pipeline first")
        pipeline()
    sh([NPM, "run", "build"], cwd=FRONTEND)
    print("\nFloatWise is starting on http://localhost:8000  (Ctrl+C to stop)\n")
    sh([PY, "-m", "uvicorn", "floatwise.api.main:app", "--port", "8000"], cwd=BACKEND,
       env={"FLOATWISE_SERVE_WEB": "1"})  # fmt: skip


def dev() -> None:
    need_venv()
    api = subprocess.Popen([str(PY), "-m", "uvicorn", "floatwise.api.main:app", "--reload", "--port", "8000"],
                           cwd=BACKEND)  # fmt: skip
    try:
        sh([NPM, "run", "dev"], cwd=FRONTEND)
    finally:
        api.terminate()


def test() -> None:
    need_venv()
    sh([PY, "-m", "pytest"], cwd=BACKEND)


COMMANDS = {"setup": setup, "all": pipeline, "demo": demo, "test": test, "dev": dev}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    COMMANDS[sys.argv[1]]()
