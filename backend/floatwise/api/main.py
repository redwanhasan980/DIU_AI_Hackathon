"""FloatWise REST API (SRS §8): `uvicorn floatwise.api.main:app`. OpenAPI docs at /docs."""

import datetime as dt
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from floatwise import schemas as S
from floatwise.api.persistence import Conflict
from floatwise.api.security import SESSION_COOKIE, AccessControl
from floatwise.api.store import DateOutOfRange, Store, UnknownId
from floatwise.config import REPO_ROOT, Config, get_config
from floatwise.explain.llm import llm_available

log = logging.getLogger("floatwise.api")

Day = Annotated[dt.date | None, Query(description="decision date (default: demo date)")]


def load_env_file(path: Path = REPO_ROOT / ".env") -> None:
    """Minimal .env loader (keeps secrets out of code, R-SEC-1). Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
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
    access = AccessControl()
    simulation_slot = threading.BoundedSemaphore(1)
    state: dict = {"store": store}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if state["store"] is None:
            state["store"] = Store(cfg)
        try:
            state["store"].warm_up(cfg.dates.demo_date)
        except Conflict:
            log.info("Operational history needs processing or reclosure; API starts with advice suspended")
        yield

    app = FastAPI(title="FloatWise API", version="1.0", lifespan=lifespan,
                  description="AI agent liquidity forecaster for upay — synthetic data only.")  # fmt: skip

    def st() -> Store:
        return state["store"]

    @app.middleware("http")
    async def protect(request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/v1/") or request.method == "OPTIONS" or path == "/api/v1/health":
            return await call_next(request)
        host = request.client.host if request.client else "unknown"
        auth_public = request.method == "POST" and path in {"/api/v1/auth/login", "/api/v1/auth/logout"}
        # Ignore forwarding headers: trust is established at the actual transport boundary.
        principal = access.authenticate(request.headers.get("authorization", ""), host)
        cookie = request.cookies.get(SESSION_COOKIE, "")
        if principal is None and cookie:
            principal = access.session_principal(st().operations.session_account(cookie))
        identity = principal.subject if principal else f"unauthenticated:{host}"
        if not st().operations.allow_request(identity, int(time.time() // 60), cfg.api.requests_per_minute):
            response = _error(429, "rate_limited", "Request limit reached; retry after one minute")
            response.headers["Retry-After"] = "60"
            return response
        if path == "/api/v1/auth/login" and not st().operations.allow_request(
            f"login:{host}", int(time.time() // 60), cfg.api.login_requests_per_minute
        ):
            response = _error(429, "rate_limited", "Too many sign-in attempts; retry after one minute")
            response.headers["Retry-After"] = "60"
            return response
        if request.method == "POST" and (auth_public or cookie):
            origin = request.headers.get("origin")
            allowed_origins = {*cfg.api.cors_origins, f"{request.url.scheme}://{request.url.netloc}"}
            if request.headers.get("X-FloatWise-CSRF") != "1" or (origin and origin not in allowed_origins):
                return _error(403, "forbidden", "The request's origin or CSRF header is invalid")
        if principal is None and not auth_public:
            st().operations.audit(identity, "authentication_denied", path, {})
            response = _error(401, "unauthorized", "Sign in with a valid account to access this endpoint")
            response.headers["WWW-Authenticate"] = "Bearer"
            return response
        if not auth_public and not access.allowed(principal, request.method, path):
            st().operations.audit(identity, "authorization_denied", path, {"method": request.method})
            return _error(403, "forbidden", "Your role does not permit this operation")
        request.state.principal = principal
        if request.method == "POST":
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > cfg.api.max_body_bytes:
                    return _error(413, "body_too_large", "Request body exceeds the configured limit")
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(Conflict)
    async def _conflict(_: Request, e: Conflict):
        return _error(409, "conflict", str(e))

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
        response = _error(e.status_code, "http_error", str(e.detail))
        response.headers.update(e.headers or {})
        return response

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
        s.integration.sync_model()
        return {"status": "ok", "model_version": s.models.version, "data_start": cfg.dates.start,
                "data_end": cfg.dates.end, "forecast_start": s.first_date, "forecast_end": s.last_date,
                "demo_date": cfg.dates.demo_date, "llm_available": llm_available(), "auth_mode": access.mode}  # fmt: skip

    @app.get(f"{p}/auth/me", response_model=S.AuthSession)
    def auth_session(request: Request):
        principal = request.state.principal
        return {"subject": principal.subject, "role": principal.role, "auth_mode": access.mode}

    @app.post(f"{p}/auth/login", response_model=S.AuthSession)
    def login(body: S.LoginRequest, request: Request, response: Response):
        principal = access.login(body.username.strip(), body.password.get_secret_value())
        if principal is None:
            st().operations.audit(f"unauthenticated:{request.client.host}", "login_failed", "session", {})
            raise HTTPException(401, "Invalid username or password")
        token = st().operations.create_session(
            principal.subject,
            access.account_fingerprint(principal.subject),
            cfg.api.session_ttl_seconds,
            request.cookies.get(SESSION_COOKIE, ""),
        )
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=cfg.api.session_ttl_seconds,
            path="/api/v1",
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
        )
        return {"subject": principal.subject, "role": principal.role, "auth_mode": access.mode}

    @app.post(f"{p}/auth/logout", response_model=S.LogoutResult)
    def logout(request: Request, response: Response):
        st().operations.revoke_session(request.cookies.get(SESSION_COOKIE, ""))
        response.delete_cookie(
            SESSION_COOKIE,
            path="/api/v1",
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
        )
        return {"status": "ok"}

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

    @app.get(f"{p}/simulate", response_model=S.SimulationResult)
    def cached_simulation():
        cached = st().simulation_default
        if cached is None:
            raise HTTPException(503, "Default simulation is unavailable; ask an operator to generate it")
        return {**cached, "source": "cache"}

    @app.post(f"{p}/simulate", response_model=S.SimulationResult)
    def simulate(req: S.SimulationRequest | None = None):
        if not simulation_slot.acquire(blocking=False):
            raise HTTPException(429, "A simulation is running; retry when it completes")
        try:
            return st().simulate((req or S.SimulationRequest()).model_dump())
        finally:
            simulation_slot.release()

    @app.get(f"{p}/metrics/model")
    def metrics():
        s = st()
        return {"metrics": s.metrics, "fairness": s.fairness, "policy_tuning": s.policy_tuning,
                "assumptions": {"business": cfg.business.model_dump(), "dso": cfg.policy.dso.model_dump(),
                                "policy": cfg.policy.floatwise.model_dump()}}  # fmt: skip

    @app.get(f"{p}/metrics/validation", response_model=S.ValidationReport)
    def validation_report():
        import json

        def artifact(name: str):
            path = cfg.artifacts_dir / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

        return {"validation": artifact("judge_validation.json"), "scale": artifact("scale_benchmark.json")}

    @app.get(f"{p}/calendar", response_model=list[S.EventInfo])
    def calendar(date: Day = None, within_days: Annotated[int, Query(ge=1, le=365)] = 45):
        from floatwise.data.calendar_bd import upcoming_events

        return [
            {"name": n, "date": e, "days_to": k} for n, e, k in upcoming_events(cfg, day(date), within_days)
        ]

    @app.post(f"{p}/decisions", response_model=S.Decision)
    def decide(body: S.DecisionIn, request: Request):
        day(body.date)
        idem = request.headers.get("Idempotency-Key")
        if idem is not None and (not idem or len(idem) > 128):
            raise HTTPException(422, "Idempotency-Key must contain 1 to 128 characters")
        replay = st().operations.replay_decision(body.model_dump(), request.state.principal.subject, idem)
        if replay:
            return replay
        with st().operations.connect() as db:
            integrated_revision = st().integration.revision(db, body.agent_id)
        if access.mode == "required" or integrated_revision or body.history_revision is not None:
            rec = st().recommendation(body.agent_id, body.date)
            if body.balance_version is None:
                raise HTTPException(422, "balance_version is required when recording a secured decision")
            if body.balance_version != rec["balance_version"]:
                raise Conflict("Balance changed; reload the recommendation before recording a decision")
            if body.action != rec["action"] or body.recommended_amount != rec["amount"]:
                raise Conflict("Recommendation changed; reload it before recording a decision")
            for field in ("history_revision", "model_version", "policy_version"):
                if getattr(body, field) != rec[field]:
                    raise Conflict("Recommendation provenance changed; reload before recording a decision")
            if body.decision == "approve" and body.final_amount != body.recommended_amount:
                raise HTTPException(422, "An approval must preserve the recommended amount")
            if body.decision == "reject" and body.final_amount != 0:
                raise HTTPException(422, "A rejection must have a zero final amount")
            if body.final_amount > st().capacity[st().agent_index(body.agent_id)]:
                raise HTTPException(422, "Final amount exceeds the agent's float capacity")
            available = rec["open_efloat"] if body.action == "TOP_UP_CASH" else rec["open_cash"]
            if body.action in {"TOP_UP_CASH", "TOP_UP_EFLOAT"} and body.final_amount > available:
                raise HTTPException(422, "The requested exchange exceeds the available opposite balance")
        return st().add_decision(
            {**body.model_dump(), "decided_at": dt.datetime.now(dt.UTC).replace(microsecond=0)},
            request.state.principal.subject,
            idem,
        )

    @app.post(f"{p}/integration/events", response_model=S.EventReceipt)
    def receive_event(body: S.IntegrationEvent, request: Request):
        return st().integration.submit(body, request.state.principal.subject)

    @app.get(f"{p}/integration/events", response_model=list[S.EventReceipt])
    def event_receipts():
        return st().integration.status()["events"]

    @app.post(f"{p}/integration/events/{{receipt_id}}/retry", response_model=S.EventReceipt)
    def retry_event(receipt_id: int, request: Request):
        return st().integration.retry(receipt_id, request.state.principal.subject)

    @app.get(f"{p}/integration/status", response_model=S.IntegrationStatus)
    def integration_status():
        return st().integration.status()

    @app.post(f"{p}/integration/connector", response_model=S.ConnectorState)
    def connector(body: S.ConnectorRequest, request: Request):
        if body.action in {"start", "resume", "replay"} and not os.environ.get("FLOATWISE_INTEGRATION_TOKEN"):
            raise HTTPException(503, "Configure the local connector with python run.py integration-setup and restart API/worker")
        return st().integration.connector(body.model_dump(), request.state.principal.subject)

    @app.get(f"{p}/integration/tasks", response_model=list[S.DsoTask])
    def tasks():
        return st().integration.status()["tasks"]

    @app.post(f"{p}/integration/tasks", response_model=S.DsoTask)
    def create_task(body: S.TaskCreate, request: Request):
        return st().integration.create_task(body.decision_id, request.state.principal.subject)

    @app.post(f"{p}/integration/tasks/{{task_id}}/status", response_model=S.DsoTask)
    def update_task(task_id: int, body: S.TaskUpdate, request: Request):
        return st().integration.transition(task_id, body.status, body.expected_version, request.state.principal.subject)

    @app.post(f"{p}/integration/tasks/{{task_id}}/simulate-delivery", response_model=S.EventReceipt)
    def simulate_delivery(task_id: int, body: S.DeliveryRequest, request: Request):
        with st().operations.connect() as db:
            replay = db.execute("SELECT id FROM integration_events WHERE source='simulated-dso' AND event_id=?",
                                (f"delivery:{task_id}:{body.expected_version}",)).fetchone()
            if replay:
                return st().integration.receipt(db, replay[0], True)
        event = st().integration.delivery_event(task_id, body.expected_version)
        return st().integration.submit(event, request.state.principal.subject)

    @app.post(f"{p}/operations/forecast", response_model=S.LiveForecast)
    def live_forecast(body: S.LiveForecastRequest, request: Request):
        result = st().live_forecast(body.agent_id, day(body.date))
        st().operations.audit(
            request.state.principal.subject,
            "live_inference",
            body.agent_id,
            {"date": str(body.date), "model_version": result["model_version"]},
        )
        return result

    @app.get(f"{p}/operations/balances/{{agent_id}}", response_model=S.BalanceState)
    def get_balance(agent_id: str, date: Day = None):
        return st().balance(agent_id, day(date))

    @app.post(f"{p}/operations/balances", response_model=S.BalanceState)
    def observe_balance(body: S.BalanceObservation, request: Request):
        try:
            return st().observe_balance(body.model_dump(), request.state.principal.subject)
        except ValueError as e:
            if isinstance(e, (Conflict, DateOutOfRange)):
                raise
            raise HTTPException(422, str(e)) from e

    @app.get(f"{p}/operations/audit", response_model=list[S.AuditEvent])
    def audit(limit: Annotated[int, Query(ge=1, le=1000)] = 100):
        return st().operations.audit_events(limit)

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
            if path.startswith("api/"):
                raise HTTPException(404, "Unknown API endpoint")
            f = (dist / path).resolve()
            if not f.is_relative_to(dist.resolve()):
                raise HTTPException(404, "Unknown file")
            return FileResponse(f if path and f.is_file() else dist / "index.html")

    # Outer CORS middleware includes the allowed origin on auth/limit errors, too.
    app.add_middleware(CORSMiddleware, allow_origins=cfg.api.cors_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "X-FloatWise-CSRF"],
                       allow_credentials=True)  # fmt: skip
    return app


app = create_app()
