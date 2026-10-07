// API client. Falls back to bundled fixtures when the API is unreachable (RULES.md R-API-2).
import type {
  AgentDetail,
  AgentSummary,
  AuthSession,
  BalanceState,
  Decision,
  DecisionIn,
  DecisionSummary,
  DsoInfo,
  DsoPlan,
  Explanation,
  Forecast,
  Health,
  Lang,
  LiveForecast,
  LoginRequest,
  LogoutResult,
  ModelReport,
  NetworkSummary,
  Recommendation,
  SimulationRequest,
  SimulationResult,
  ValidationReport,
  IntegrationEvent,
  IntegrationStatus,
  ConnectorState,
  EventReceipt,
  DsoTask,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL ?? "") + "/api/v1";
let authenticatedSession = false;
let sessionRevision = 0;
export function setSessionActive(active: boolean) {
  authenticatedSession = active;
  sessionRevision += 1;
  window.dispatchEvent(new Event("fw-auth"));
}

// Fixtures are exported from the real API for the demo date (backend/scripts/export_fixtures.py).
const fixtures = import.meta.glob<{ default: unknown }>("../fixtures/*.json", { eager: true });

function fixtureFor(path: string): unknown {
  const key = path.replace(/^\//, "").replace(/[/?=&]/g, "_");
  const hit = fixtures[`../fixtures/${key}.json`];
  return hit ? hit.default : undefined;
}

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

let usingFixtures = false;
export const isUsingFixtures = () => usingFixtures;
const markFixtures = () => {
  if (!usingFixtures) {
    usingFixtures = true;
    window.dispatchEvent(new Event("fw-fixtures"));
  }
};

async function request<T>(path: string, init?: RequestInit, allowFixtures = true, timeoutMs?: number): Promise<T> {
  const revision = sessionRevision;
  const offline = (): T => {
    if (!allowFixtures || authenticatedSession || !(import.meta.env.DEV || import.meta.env.VITE_OFFLINE_DEMO === "1")
      || (init?.method && init.method !== "GET" && (path !== "/simulate" || init.body !== "{}"))) {
      throw new ApiError("offline", "The API is unreachable. This operation requires a live connection.");
    }
    const fx = fixtureFor(path);
    if (fx !== undefined) {
      markFixtures();
      return fx as T;
    }
    throw new ApiError("offline", "The FloatWise API is not reachable. Start it with `make api`.");
  };
  let res: Response;
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (init?.method === "POST") headers.set("X-FloatWise-CSRF", "1");
  const controller = new AbortController();
  const timeout = timeoutMs ? window.setTimeout(() => controller.abort(), timeoutMs) : undefined;
  try {
    res = await fetch(BASE + path, { ...init, headers, credentials: "include", signal: init?.signal ?? controller.signal });
  } catch {
    return offline();
  } finally {
    if (timeout !== undefined) window.clearTimeout(timeout);
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    if (path.startsWith("/auth/") && res.status === 404) {
      throw new ApiError("auth_api_outdated", "The running API needs a restart to enable sign-in.");
    }
    if (res.status === 401 && path !== "/auth/login" && authenticatedSession && revision === sessionRevision) {
      window.dispatchEvent(new Event("fw-auth-expired"));
    }
    const err = (body as { error?: { code: string; message: string } } | null)?.error;
    if (!err && ![401, 403, 429].includes(res.status)) return offline();
    throw new ApiError(err?.code ?? "http_error", err?.message ?? `Request failed (${res.status})`);
  }
  if (!allowFixtures && usingFixtures) {
    usingFixtures = false;
    window.dispatchEvent(new Event("fw-fixtures"));
  }
  return body as T;
}

const q = (params: Record<string, string | number | undefined | null>) => {
  const s = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join("&");
  return s ? `?${s}` : "";
};

export const api = {
  health: () => request<Health>("/health", undefined, true, 10000),
  // Identity is always checked against the live API, never a bundled fixture.
  authMe: () => request<AuthSession>("/auth/me", undefined, false, 10000),
  login: (body: LoginRequest) => request<AuthSession>("/auth/login", { method: "POST", body: JSON.stringify(body) }, false, 10000),
  logout: () => request<LogoutResult>("/auth/logout", { method: "POST" }, false, 10000),
  network: (date: string) => request<NetworkSummary>(`/network/summary${q({ date })}`),
  agents: (date: string, filters: { district?: string; archetype?: string; dso_id?: string } = {}) =>
    request<AgentSummary[]>(`/agents${q({ date, ...filters })}`),
  agent: (id: string, date: string) => request<AgentDetail>(`/agents/${id}${q({ date })}`),
  forecast: (id: string, date: string) => request<Forecast>(`/agents/${id}/forecast${q({ date })}`),
  recommendation: (id: string, date: string) =>
    request<Recommendation>(`/agents/${id}/recommendation${q({ date })}`),
  explanation: (id: string, date: string, lang: Lang) =>
    request<Explanation>(`/agents/${id}/explanation${q({ date, lang })}`),
  dsos: (date: string) => request<DsoInfo[]>(`/dsos${q({ date })}`),
  dsoPlan: (id: string, date: string, maxVisits?: number, maxCash?: number) =>
    request<DsoPlan>(`/dso/${id}/plan${q({ date, max_visits: maxVisits, max_cash: maxCash })}`),
  simulate: (body: SimulationRequest = {}) =>
    request<SimulationResult>("/simulate", { method: "POST", body: JSON.stringify(body) }),
  cachedSimulation: () => request<SimulationResult>("/simulate"),
  modelReport: () => request<ModelReport>("/metrics/model"),
  validationReport: () => request<ValidationReport>("/metrics/validation"),
  liveForecast: (agent_id: string, date: string) => request<LiveForecast>("/operations/forecast", { method: "POST", body: JSON.stringify({ agent_id, date }) }),
  balance: (id: string, date: string) => request<BalanceState>(`/operations/balances/${id}${q({ date })}`),
  observeBalance: (agent_id: string, date: string, cash: number, efloat: number, expected_version: number) =>
    request<BalanceState>("/operations/balances", { method: "POST", body: JSON.stringify({ agent_id, date, cash, efloat, expected_version }) }),
  decide: (body: DecisionIn, key: string = crypto.randomUUID()) => request<Decision>("/decisions", {
    method: "POST", body: JSON.stringify(body), headers: { "Idempotency-Key": key },
  }),
  decisions: () => request<Decision[]>("/decisions"),
  decisionSummary: () => request<DecisionSummary>("/decisions/summary"),
  integrationStatus: () => request<IntegrationStatus>("/integration/status", undefined, true, 10000),
  connector: (agent_id: string, date: string, action: "start" | "pause" | "resume" | "replay") =>
    request<ConnectorState>("/integration/connector", { method: "POST", body: JSON.stringify({ agent_id, date, action }) }, false),
  integrationEvent: (event: IntegrationEvent) => request<EventReceipt>("/integration/events", { method: "POST", body: JSON.stringify(event) }, false),
  retryEvent: (id: number) => request<EventReceipt>(`/integration/events/${id}/retry`, { method: "POST" }, false),
  createTask: (decision_id: number) => request<DsoTask>("/integration/tasks", { method: "POST", body: JSON.stringify({ decision_id }) }, false),
  taskStatus: (task: DsoTask, status: "dispatched" | "accepted" | "rejected" | "cancelled") =>
    request<DsoTask>(`/integration/tasks/${task.id}/status`, { method: "POST", body: JSON.stringify({ status, expected_version: task.version }) }, false),
  deliverTask: (task: DsoTask) => request<EventReceipt>(`/integration/tasks/${task.id}/simulate-delivery`, {
    method: "POST", body: JSON.stringify({ expected_version: task.version }),
  }, false),
};
