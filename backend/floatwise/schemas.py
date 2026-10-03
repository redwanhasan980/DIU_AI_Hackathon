"""API contracts (SRS §8). Mirrored by frontend/src/api/types.ts — change both together (R-API-1)."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["TOP_UP_CASH", "TOP_UP_EFLOAT", "NO_ACTION", "NEEDS_EXTRA_FLOAT"]
RiskBand = Literal["low", "medium", "high"]
Lang = Literal["bn", "en"]


class Quantiles(BaseModel):
    p10: int
    p50: int
    p90: int


class AgentSummary(BaseModel):
    agent_id: str
    shop_name: str
    archetype: str
    division: str
    district: str
    upazila: str
    lat: float
    lon: float
    dso_id: str
    distributor_id: str
    float_capacity: int
    p_stockout: float = Field(description="max(p_cash_stockout, p_efloat_stockout) for the next day")
    risk_band: RiskBand
    action: Action
    amount: int


class HistoryPoint(BaseModel):
    date: dt.date
    cashout_amt: int
    cashin_amt: int
    close_cash: int
    close_efloat: int
    stockout_cash: bool
    stockout_efloat: bool


class AgentDetail(BaseModel):
    agent: AgentSummary
    date: dt.date
    close_cash: int
    close_efloat: int
    history: list[HistoryPoint]


class ForecastPoint(BaseModel):
    date: dt.date
    horizon: int
    cashout: Quantiles
    cashin: Quantiles
    actual_cashout: int | None = Field(None, description="synthetic ground-truth demand (backtest view)")
    actual_cashin: int | None = None


class Forecast(BaseModel):
    agent_id: str
    origin: dt.date
    points: list[ForecastPoint]


class OutlookDay(BaseModel):
    date: dt.date
    p_cash_stockout: float
    p_efloat_stockout: float
    cash_need: int
    efloat_need: int
    at_risk: bool


class Recommendation(BaseModel):
    agent_id: str
    date: dt.date = Field(description="decision date (balances at close of this day)")
    effective_date: dt.date = Field(description="day the rebalance takes effect")
    action: Action
    amount: int
    open_cash: int
    open_efloat: int
    cash_target: int
    efloat_target: int
    p_cash_stockout: float
    p_efloat_stockout: float
    extra_float_needed: int
    service_level: float
    reason_codes: list[str]
    outlook: list[OutlookDay]
    first_risk_date: dt.date | None


class Driver(BaseModel):
    feature: str
    label: str
    value: str
    contribution_bdt: int


class Explanation(BaseModel):
    agent_id: str
    date: dt.date
    lang: Lang
    base_bdt: int
    forecast_p50_bdt: int
    drivers: list[Driver]
    narrative: str
    source: Literal["cache", "llm", "template"]


class PlanVisit(BaseModel):
    rank: int
    agent_id: str
    shop_name: str
    upazila: str
    lat: float
    lon: float
    action: Action
    amount: int
    p_stockout: float
    priority_bdt: int


class PlanExcluded(BaseModel):
    agent_id: str
    shop_name: str
    action: Action
    amount: int
    p_stockout: float
    priority_bdt: int
    reason: str


class DsoPlan(BaseModel):
    dso_id: str
    date: dt.date
    max_visits: int
    max_cash: int
    cash_to_carry: int
    efloat_to_send: int
    visits: list[PlanVisit]
    excluded: list[PlanExcluded]


class DsoInfo(BaseModel):
    dso_id: str
    district: str
    n_agents: int
    n_at_risk: int


class EventInfo(BaseModel):
    name: str
    date: dt.date
    days_to: int


class DistrictRisk(BaseModel):
    district: str
    n_agents: int
    n_high: int
    n_medium: int
    recommended_cash: int
    recommended_efloat: int


class NetworkSummary(BaseModel):
    date: dt.date
    n_agents: int
    by_band: dict[str, int]
    by_action: dict[str, int]
    recommended_cash: int
    recommended_efloat: int
    by_district: list[DistrictRisk]
    upcoming_events: list[EventInfo]


class SimulationRequest(BaseModel):
    service_level: float | None = Field(None, ge=0.5, le=0.995)
    risk_threshold: float | None = Field(None, ge=0.0, le=1.0)
    overlap_alpha: float | None = Field(None, ge=0.0, le=1.0)
    max_visits: int | None = Field(None, ge=0, le=100)
    max_cash: int | None = Field(None, ge=0, le=100_000_000)
    start: dt.date | None = None
    end: dt.date | None = None


class PolicyMetrics(BaseModel):
    stockout_agent_days: int
    cash_stockout_days: int
    efloat_stockout_days: int
    failed_cashout_count: int
    failed_cashout_bdt: int
    failed_cashin_count: int
    failed_cashin_bdt: int
    lost_commission_bdt: int
    customers_at_risk: int
    avg_cash_held_bdt: int
    rebalancing_trips: int
    served_share: float


class TimelinePoint(BaseModel):
    date: dt.date
    status_quo_stockouts: int
    floatwise_stockouts: int
    status_quo_failed_bdt: int
    floatwise_failed_bdt: int


class SegmentResult(BaseModel):
    segment: str
    n_agents: int
    status_quo_stockouts: int
    floatwise_stockouts: int
    stockout_reduction_pct: float
    status_quo_failed_bdt: int
    floatwise_failed_bdt: int


class SweepPoint(BaseModel):
    service_level: float
    stockout_agent_days: int
    failed_bdt: int
    avg_cash_held_bdt: int
    rebalancing_trips: int


class SimulationResult(BaseModel):
    start: dt.date
    end: dt.date
    n_agents: int
    params: dict[str, float]
    status_quo: PolicyMetrics
    floatwise: PolicyMetrics
    improvement_pct: dict[str, float]
    per_1000_agents_month: dict[str, int]
    timeline: list[TimelinePoint]
    by_archetype: list[SegmentResult]
    by_area_type: list[SegmentResult]
    sweep: list[SweepPoint] = []
    source: Literal["cache", "live"] = "live"


class DecisionIn(BaseModel):
    agent_id: str = Field(pattern=r"^AG\d{5}$")
    date: dt.date
    action: Action
    recommended_amount: int = Field(ge=0)
    final_amount: int = Field(ge=0, le=100_000_000)
    decision: Literal["approve", "modify", "reject"]
    reason: str = Field("", max_length=300)


class Decision(DecisionIn):
    decided_at: dt.datetime


class ReasonCount(BaseModel):
    reason: str
    count: int


class DecisionSummary(BaseModel):
    """Feedback signal from human decisions (FR-HITL-3)."""

    total: int
    by_decision: dict[str, int]
    by_action: dict[str, int]
    approval_rate: float = Field(description="approve / total")
    avg_modify_change_pct: float | None = Field(
        None, description="mean (final - recommended) / recommended for modify"
    )
    recommended_bdt: int
    final_bdt: int
    top_rejection_reasons: list[ReasonCount]


class Health(BaseModel):
    status: str
    model_version: str
    data_start: dt.date
    data_end: dt.date
    forecast_start: dt.date
    forecast_end: dt.date
    demo_date: dt.date
    llm_available: bool
