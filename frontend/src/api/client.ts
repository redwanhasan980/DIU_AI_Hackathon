// API client. Falls back to bundled fixtures when the API is unreachable (RULES.md R-API-2).
import type {
  AgentDetail,
  AgentSummary,
  Decision,
  DecisionIn,
  DsoInfo,
  DsoPlan,
  Explanation,
  Forecast,
  Health,
  Lang,
  ModelReport,
  NetworkSummary,
  Recommendation,
  SimulationRequest,
  SimulationResult,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL ?? "") + "/api/v1";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const offline = (): T => {
    const fx = fixtureFor(path);
    if (fx !== undefined) {
      markFixtures();
      return fx as T;
    }
    throw new ApiError("offline", "The FloatWise API is not reachable. Start it with `make api`.");
  };
  let res: Response;
  try {
    res = await fetch(BASE + path, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    return offline();
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (body as { error?: { code: string; message: string } } | null)?.error;
    if (!err) return offline(); // not a FloatWise API response (API down behind a proxy or static host)
    throw new ApiError(err?.code ?? "http_error", err?.message ?? `Request failed (${res.status})`);
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
  health: () => request<Health>("/health"),
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
  modelReport: () => request<ModelReport>("/metrics/model"),
  decide: (body: DecisionIn) => request<Decision>("/decisions", { method: "POST", body: JSON.stringify(body) }),
  decisions: () => request<Decision[]>("/decisions"),
};
