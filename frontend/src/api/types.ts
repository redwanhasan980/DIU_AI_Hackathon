// Mirror of backend/floatwise/schemas.py — change both together (RULES.md R-API-1).

export type Action = "TOP_UP_CASH" | "TOP_UP_EFLOAT" | "NO_ACTION" | "NEEDS_EXTRA_FLOAT";
export type RiskBand = "low" | "medium" | "high";
export type Lang = "bn" | "en";

export interface AuthSession {
  subject: string;
  role: "viewer" | "operator" | "admin";
  auth_mode: "demo" | "required";
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LogoutResult {
  status: "ok";
}

export interface Quantiles {
  p10: number;
  p50: number;
  p90: number;
}

export interface AgentSummary {
  agent_id: string;
  shop_name: string;
  archetype: string;
  division: string;
  district: string;
  upazila: string;
  lat: number;
  lon: number;
  dso_id: string;
  distributor_id: string;
  float_capacity: number;
  p_stockout: number;
  risk_band: RiskBand;
  action: Action;
  amount: number;
}

export interface HistoryPoint {
  date: string;
  cashout_amt: number;
  cashin_amt: number;
  close_cash: number;
  close_efloat: number;
  stockout_cash: boolean;
  stockout_efloat: boolean;
}

export interface AgentDetail {
  agent: AgentSummary;
  date: string;
  close_cash: number;
  close_efloat: number;
  history: HistoryPoint[];
}

export interface ForecastPoint {
  date: string;
  horizon: number;
  cashout: Quantiles;
  cashin: Quantiles;
  actual_cashout: number | null;
  actual_cashin: number | null;
}

export interface Forecast {
  agent_id: string;
  origin: string;
  points: ForecastPoint[];
  source: "precomputed" | "live";
  model_version: string;
  history_revision: number;
  balance_revision: number;
  policy_version: string;
}

export interface OutlookDay {
  date: string;
  p_cash_stockout: number;
  p_efloat_stockout: number;
  cash_need: number;
  efloat_need: number;
  at_risk: boolean;
}

export interface Recommendation {
  balance_version: number;
  history_revision: number;
  model_version: string;
  policy_version: string;
  agent_id: string;
  date: string;
  effective_date: string;
  action: Action;
  amount: number;
  open_cash: number;
  open_efloat: number;
  cash_target: number;
  efloat_target: number;
  p_cash_stockout: number;
  p_efloat_stockout: number;
  extra_float_needed: number;
  service_level: number;
  reason_codes: string[];
  outlook: OutlookDay[];
  first_risk_date: string | null;
}

export interface Driver {
  feature: string;
  label: string;
  value: string;
  contribution_bdt: number;
}

export interface Explanation {
  agent_id: string;
  date: string;
  lang: Lang;
  base_bdt: number;
  forecast_p50_bdt: number;
  drivers: Driver[];
  narrative: string;
  source: "cache" | "llm" | "template";
}

export interface PlanVisit {
  rank: number;
  agent_id: string;
  shop_name: string;
  upazila: string;
  lat: number;
  lon: number;
  action: Action;
  amount: number;
  p_stockout: number;
  priority_bdt: number;
}

export interface PlanExcluded {
  agent_id: string;
  shop_name: string;
  action: Action;
  amount: number;
  p_stockout: number;
  priority_bdt: number;
  reason: string;
}

export interface DsoPlan {
  dso_id: string;
  date: string;
  max_visits: number;
  max_cash: number;
  cash_to_carry: number;
  efloat_to_send: number;
  visits: PlanVisit[];
  excluded: PlanExcluded[];
}

export interface DsoInfo {
  dso_id: string;
  district: string;
  n_agents: number;
  n_at_risk: number;
}

export interface EventInfo {
  name: string;
  date: string;
  days_to: number;
}

export interface DistrictRisk {
  district: string;
  n_agents: number;
  n_high: number;
  n_medium: number;
  recommended_cash: number;
  recommended_efloat: number;
}

export interface NetworkSummary {
  date: string;
  n_agents: number;
  by_band: Record<RiskBand, number>;
  by_action: Partial<Record<Action, number>>;
  recommended_cash: number;
  recommended_efloat: number;
  by_district: DistrictRisk[];
  upcoming_events: EventInfo[];
}

export interface SimulationRequest {
  service_level?: number;
  risk_threshold?: number;
  overlap_alpha?: number;
  max_visits?: number;
  max_cash?: number;
  start?: string;
  end?: string;
}

export interface PolicyMetrics {
  stockout_agent_days: number;
  cash_stockout_days: number;
  efloat_stockout_days: number;
  failed_cashout_count: number;
  failed_cashout_bdt: number;
  failed_cashin_count: number;
  failed_cashin_bdt: number;
  lost_commission_bdt: number;
  lost_upay_fee_bdt: number;
  customers_at_risk: number;
  avg_cash_held_bdt: number;
  rebalancing_trips: number;
  served_share: number;
}

export interface TimelinePoint {
  date: string;
  status_quo_stockouts: number;
  floatwise_stockouts: number;
  status_quo_failed_bdt: number;
  floatwise_failed_bdt: number;
}

export interface SegmentResult {
  segment: string;
  n_agents: number;
  status_quo_stockouts: number;
  floatwise_stockouts: number;
  stockout_reduction_pct: number;
  status_quo_failed_bdt: number;
  floatwise_failed_bdt: number;
}

export interface SweepPoint {
  service_level: number;
  stockout_agent_days: number;
  failed_bdt: number;
  avg_cash_held_bdt: number;
  rebalancing_trips: number;
}

export interface SimulationResult {
  start: string;
  end: string;
  n_agents: number;
  params: Record<string, number>;
  status_quo: PolicyMetrics;
  floatwise: PolicyMetrics;
  improvement_pct: Record<string, number>;
  per_1000_agents_month: Record<string, number>;
  upay_network_month: Record<string, number>;
  timeline: TimelinePoint[];
  by_archetype: SegmentResult[];
  by_area_type: SegmentResult[];
  sweep: SweepPoint[];
  source: "cache" | "live";
}

export interface DecisionIn {
  balance_version?: number | null;
  history_revision?: number | null;
  model_version?: string | null;
  policy_version?: string | null;
  agent_id: string;
  date: string;
  action: Action;
  recommended_amount: number;
  final_amount: number;
  decision: "approve" | "modify" | "reject";
  reason: string;
}

export interface Decision extends DecisionIn {
  decided_at: string;
  decision_id?: number | null;
}

export interface DecisionSummary {
  total: number;
  by_decision: Record<"approve" | "modify" | "reject", number>;
  by_action: Partial<Record<Action, number>>;
  approval_rate: number;
  avg_modify_change_pct: number | null;
  recommended_bdt: number;
  final_bdt: number;
  top_rejection_reasons: { reason: string; count: number }[];
}

export interface Health {
  status: string;
  model_version: string;
  data_start: string;
  data_end: string;
  forecast_start: string;
  forecast_end: string;
  demo_date: string;
  llm_available: boolean;
  auth_mode: "demo" | "required";
}

export interface LiveForecast extends Forecast {
  source: "live";
  model_version: string;
  history_revision: number;
  balance_revision: number;
  policy_version: string;
}

export interface BalanceState {
  cash: number;
  efloat: number;
  version: number;
}

export interface AuditEvent {
  id: number;
  at: string;
  actor: string;
  event: string;
  resource: string;
  details: Record<string, unknown>;
}

export interface ValidationSlice {
  n: number;
  wape: number;
  coverage: number;
  width_bdt: number;
  pinball: number;
}

type ValidationMetrics = Record<"cashout" | "cashin", Record<string, ValidationSlice>>;

export interface ValidationReport {
  validation: {
    data_kind: "synthetic";
    assessment_period: string[];
    calibration_period: string[];
    test_period_used: boolean;
    calibration: { raw: ValidationMetrics; calibrated: ValidationMetrics; production_promoted: boolean };
    feature_ablations: Record<string, { removed_features: string[]; metrics: ValidationMetrics }>;
    pipeline_ablations: Record<string, PolicyMetrics>;
    robustness: { protocol: string; scenarios: Record<string, ValidationMetrics> };
    business_sensitivity: (PolicyMetrics & { compliance: number; churn_probability: number })[];
    limitations: string[];
  } | null;
  scale: {
    limitations: string;
    populations: { n_agents: number; forecast_rows: number; median_seconds: Record<string, number> }[];
  } | null;
}

export interface SliceMetrics {
  n: number;
  wape_model: number;
  mae_model: number;
  coverage_p10_p90: number;
  wape_seasonal_naive: number;
  wape_trailing_mean7: number;
  improvement_vs_seasonal_naive_pct: number;
  improvement_vs_trailing_mean7_pct: number;
}

export interface FairnessSegment extends SegmentResult {
  wape_model: number;
  wape_seasonal_naive: number;
  forecast_beats_baseline: boolean;
  service_not_worse: boolean;
}

export interface ModelReport {
  metrics: {
    version: string;
    test: Record<"cashout" | "cashin", Record<string, SliceMetrics>>;
    acceptance: { checks: Record<string, boolean>; all_passed: boolean };
  };
  fairness: { segments: FairnessSegment[]; flagged_segments: string[]; all_segments_ok: boolean } | null;
  policy_tuning: {
    period: string;
    rule: string;
    selected: { service_level: number; risk_threshold: number; stockout_reduction_pct: number };
  } | null;
  assumptions: {
    business: Record<string, number>;
    dso: Record<string, number>;
    policy: Record<string, number>;
  };
}

export type IntegrationPayload =
  | { kind: "transaction"; side: "cashin" | "cashout"; outcome: "served" | "denied"; amount: number; failure_code?: "liquidity" | "network" | "identity" | "limit" | null }
  | { kind: "balance_snapshot"; cash: number; efloat: number; sequence: number }
  | { kind: "day_closed" }
  | { kind: "delivery_confirmation"; task_id: number; reference: string; cash: number; efloat: number };
export interface IntegrationEvent {
  schema_version?: 1;
  source: "simulated-upstream" | "simulated-dso";
  event_id: string;
  occurred_at: string;
  agent_id: string;
  payload: IntegrationPayload;
}
export interface EventReceipt {
  id: number; source: string; event_id: string; agent_id: string; kind: string;
  occurred_at: string; received_at: string; status: "pending" | "processed" | "failed";
  attempts: number; error: string | null; processed_at: string | null; duplicate: boolean;
}
export interface ConnectorState {
  run_id: string | null; agent_id: string | null; date: string | null;
  status: "idle" | "running" | "paused" | "completed" | "failed";
  cursor: number; total: number; error: string | null;
}
export interface DsoTask {
  id: number; decision_id: number; agent_id: string; dso_id: string; date: string;
  action: Action; amount: number;
  status: "approved" | "dispatched" | "accepted" | "completed" | "rejected" | "cancelled";
  version: number; history_revision: number; balance_revision: number;
  model_version: string; policy_version: string; delivery_reference: string | null;
  created_at: string; updated_at: string;
}
export interface IntegrationStatus {
  simulated: true;
  connector: ConnectorState;
  worker: { heartbeat_at: string | null; online: boolean; connector_configured: boolean };
  metrics: { queue_depth: number; processed: number; failed: number; retries: number;
    oldest_pending_seconds: number; average_processing_seconds: number;
    inference_count: number; inference_errors: number; inference_p95_ms: number;
    reconciliation_failures: number; stale_forecasts: number };
  drift: { status: "insufficient_data" | "within_reference" | "review_required";
    sample_count: number; minimum_samples: number; threshold: number;
    cashin_mean_ratio_change: number | null; cashout_mean_ratio_change: number | null; note: string };
  active_model: string;
  models: { version: string; registered_at: string; training_cutoff: string;
    feature_schema: string; binary_sha256: string; evaluation: Record<string, unknown> }[];
  events: EventReceipt[];
  tasks: DsoTask[];
}
