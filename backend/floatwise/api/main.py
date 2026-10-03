"""FloatWise REST API (SRS §8): `uvicorn floatwise.api.main:app`. OpenAPI docs at /docs."""

import datetime as dt
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from floatwise import schemas as S
from floatwise.api.store import DateOutOfRange, Store, UnknownId
from floatwise.config import REPO_ROOT, Config, get_config
from floatwise.explain.llm import llm_available

log = logging.getLogger("floatwise.api")

Day = Annotated[dt.date | None, Query(description="decision date (default: demo date)")]


def load_env_file(path: Path = REPO_ROOT / ".env") -> None:
    """Minimal .env loader (keeps secrets out of code, R-SEC-1). Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if value.strip():
                os.environ.setdefault(key.strip(), value.strip())


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(cfg: Config | None = None, store: Store | None = None) -> FastAPI:
    load_env_file()
    cfg = cfg or get_config()
    state: dict = {"store": store}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if state["store"] is None:
            state["store"] = Store(cfg)
        state["store"].warm_up(cfg.dates.demo_date)  # first demo request stays under 300 ms (NFR-1)
        yield

    app = FastAPI(title="FloatWise API", version="1.0", lifespan=lifespan,
                  description="AI agent liquidity forecaster for upay — synthetic data only.")  # fmt: skip
    app.add_middleware(CORSMiddleware, allow_origins=cfg.api.cors_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])  # fmt: skip

    def st() -> Store:
        return state["store"]

    # ---- errors: standard shape, never leak stack traces (R-SEC-2) ----------------
    @app.exception_handler(DateOutOfRange)
    async def _date(_: Request, e: DateOutOfRange):
        return _error(422, "date_out_of_range", str(e))

    @app.exception_handler(UnknownId)
    async def _unknown(_: Request, e: UnknownId):
        return _error(404, "not_found", str(e.args[0]))

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, e: RequestValidationError):
        first = e.errors()[0] if e.errors() else {}
        where = ".".join(str(x) for x in first.get("loc", []))
        return _error(422, "invalid_request", f"{where}: {first.get('msg', 'invalid input')}")

    @app.exception_handler(HTTPException)
    async def _http(_: Request, e: HTTPException):
        return _error(e.status_code, "http_error", str(e.detail))

    @app.exception_handler(Exception)
    async def _internal(_: Request, e: Exception):
        log.exception("unhandled error")
        return _error(500, "internal_error", "Something went wrong. Check the server logs.")

    # ---- endpoints ------------------------------------------------------------------
    def day(d: dt.date | None) -> dt.date:
        d = d or cfg.dates.demo_date
        st().check_date(d)
        return d

    p = "/api/v1"

    @app.get(f"{p}/health", response_model=S.Health)
    def health():
        s = st()
        return {"status": "ok", "model_version": s.models.version, "data_start": cfg.dates.start,
                "data_end": cfg.dates.end, "forecast_start": s.first_date, "forecast_end": s.last_date,
                "demo_date": cfg.dates.demo_date, "llm_available": llm_available()}  # fmt: skip

    @app.get(f"{p}/agents", response_model=list[S.AgentSummary])
    def agents(date: Day = None, district: str | None = None, archetype: str | None = None,
               dso_id: str | None = None, risk_min: Annotated[float, Query(ge=0, le=1)] = 0.0):  # fmt: skip
        return st().list_agents(day(date), district, archetype, dso_id, risk_min)

    @app.get(f"{p}/agents/{{agent_id}}", response_model=S.AgentDetail)
    def agent(agent_id: str, date: Day = None):
        return st().agent_detail(agent_id, day(date))

    @app.get(f"{p}/agents/{{agent_id}}/forecast", response_model=S.Forecast)
    def forecast(agent_id: str, date: Day = None, horizon: Annotated[int, Query(ge=1, le=7)] = 7):
        return st().forecast(agent_id, day(date), horizon)

    @app.get(f"{p}/agents/{{agent_id}}/recommendation", response_model=S.Recommendation)
    def recommendation(agent_id: str, date: Day = None,
                       service_level: Annotated[float | None, Query(ge=0.5, le=0.995)] = None):  # fmt: skip
        return st().recommendation(agent_id, day(date), service_level)

    @app.get(f"{p}/agents/{{agent_id}}/explanation", response_model=S.Explanation)
    def explanation(agent_id: str, date: Day = None, lang: S.Lang = "bn"):
        return st().explanation(agent_id, day(date), lang)

    @app.get(f"{p}/dsos", response_model=list[S.DsoInfo])
    def dsos(date: Day = None):
        return st().dsos(day(date))

    @app.get(f"{p}/dso/{{dso_id}}/plan", response_model=S.DsoPlan)
    def dso_plan(dso_id: str, date: Day = None, max_visits: Annotated[int | None, Query(ge=0, le=100)] = None,
                 max_cash: Annotated[int | None, Query(ge=0, le=100_000_000)] = None):  # fmt: skip
        return st().dso_plan(dso_id, day(date), max_visits, max_cash)

    @app.get(f"{p}/network/summary", response_model=S.NetworkSummary)
    def network(date: Day = None):
        return st().network_summary(day(date))

    @app.post(f"{p}/simulate", response_model=S.SimulationResult)
    def simulate(req: S.SimulationRequest | None = None):
        return st().simulate((req or S.SimulationRequest()).model_dump())

    @app.get(f"{p}/metrics/model")
    def metrics():
        s = st()
        return {"metrics": s.metrics, "fairness": s.fairness, "policy_tuning": s.policy_tuning,
                "assumptions": {"business": cfg.business.model_dump(), "dso": cfg.policy.dso.model_dump(),
                                "policy": cfg.policy.floatwise.model_dump()}}  # fmt: skip

    @app.get(f"{p}/calendar", response_model=list[S.EventInfo])
    def calendar(date: Day = None, within_days: Annotated[int, Query(ge=1, le=365)] = 45):
        from floatwise.data.calendar_bd import upcoming_events

        return [
            {"name": n, "date": e, "days_to": k} for n, e, k in upcoming_events(cfg, day(date), within_days)
        ]

    @app.post(f"{p}/decisions", response_model=S.Decision)
    def decide(body: S.DecisionIn):
        day(body.date)
        return st().add_decision(
            {**body.model_dump(), "decided_at": dt.datetime.now().replace(microsecond=0)}
        )

    @app.get(f"{p}/decisions", response_model=list[S.Decision])
    def decisions():
        return st().list_decisions()

    @app.get(f"{p}/decisions/summary", response_model=S.DecisionSummary)
    def decision_summary():
        return st().decision_summary()

    # ---- optional: serve the built frontend (make demo) -----------------------------
    dist = REPO_ROOT / "frontend" / "dist"
    if os.environ.get("FLOATWISE_SERVE_WEB") == "1" and dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = dist / path
            return FileResponse(f if path and f.is_file() else dist / "index.html")

    return app


app = create_app()
