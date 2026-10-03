"""Typed loader for backend/config.yaml (the single source of constants)."""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_CONFIG_PATH = BACKEND_DIR / "config.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Paths(_Strict):
    data_dir: str
    sample_dir: str
    artifacts_dir: str


class Dates(_Strict):
    start: dt.date
    end: dt.date
    train_end: dt.date
    val_start: dt.date
    val_end: dt.date
    test_start: dt.date
    test_end: dt.date
    demo_date: dt.date


class CalendarCfg(_Strict):
    eid_fitr: list[dt.date]
    eid_adha: list[dt.date]
    ramadan_days: int
    eid_holiday_days: int
    post_eid_days: int
    pre_eid_window: int
    pre_eid_ramp: list[float]
    boishakh: str
    boishakh_window: int
    public_holidays: list[str]
    salary_window: tuple[int, int]
    salary_curve: list[float]
    weekend_dows: list[int]
    g2p_disbursement_days: list[str]
    g2p_curve: list[float]


class NetworkCfg(_Strict):
    n_agents: int
    agents_per_dso: int
    dsos_per_distributor: int
    location_jitter_deg: float
    size_factor_sigma: float
    float_capacity_range: tuple[float, float]
    archetype_share: dict[str, float]
    districts: dict[str, list[Any]]
    archetype_districts: dict[str, dict[str, float]]
    shop_prefixes: list[str]
    shop_suffixes: list[str]


class Amp(_Strict):
    co: float
    ci: float


class ArchetypeCfg(_Strict):
    base_co: float
    base_ci: float
    noise_sigma: float
    ticket: float
    dow: list[float]
    salary_amp: Amp
    g2p_amp: Amp
    eid_fitr_amp: Amp
    eid_adha_amp: Amp
    eid_holiday_mult: float
    post_eid_mult: float
    ramadan_mult: Amp
    boishakh_mult: float
    holiday_mult: float
    rural: bool


class DemandCfg(_Strict):
    annual_growth: float
    co_ci_noise_corr: float
    ticket_noise_sigma: float
    intraday_slots: int
    co_slot_profile: list[float]
    ci_slot_profile: list[float]


class ShockType(_Strict):
    mult: float
    min_days: int
    max_days: int
    months: list[int]
    districts: list[str] | str


class ShocksCfg(_Strict):
    n_shocks: int
    types: dict[str, ShockType]


class StatusQuoPolicy(_Strict):
    lookback_days: int
    target_ratio: float
    trigger_ratio: float


class FloatWisePolicy(_Strict):
    service_level: float
    risk_threshold: float
    overlap_alpha: float
    min_buffer_cash: int
    min_buffer_efloat: int
    round_to: int
    escalation_service_level: float
    outlook_days: int
    self_rebalance_compliance: float


class DsoCfg(_Strict):
    max_visits: int
    max_cash: int
    allocator: str


class PolicyCfg(_Strict):
    status_quo: StatusQuoPolicy
    floatwise: FloatWisePolicy
    dso: DsoCfg
    sweep_service_levels: list[float]


class BusinessCfg(_Strict):
    cashout_fee_rate: float
    channel_share_rate: float
    cashin_channel_rate: float
    churn_prob_after_fail: float
    customer_monthly_value: float
    idle_cash_annual_cost: float


class ModelCfg(_Strict):
    quantiles: list[float]
    targets: list[str]
    horizons: int
    scale_window: int
    min_history_days: int
    train_horizons_per_origin: int
    censoring: str
    quantile_mode: str
    event_window: tuple[int, int]
    lgbm: dict[str, Any]


class LlmCfg(_Strict):
    model_env: str
    default_model: str
    timeout_s: float
    max_tokens: int
    demo_agents_per_archetype: int


class ApiCfg(_Strict):
    cors_origins: list[str]


class Config(_Strict):
    seed: int
    paths: Paths
    dates: Dates
    calendar: CalendarCfg
    network: NetworkCfg
    archetypes: dict[str, ArchetypeCfg]
    demand: DemandCfg
    shocks: ShocksCfg
    policy: PolicyCfg
    business: BusinessCfg
    model: ModelCfg
    llm: LlmCfg
    api: ApiCfg

    # ---- resolved paths -------------------------------------------------
    @property
    def data_dir(self) -> Path:
        return _resolve(self.paths.data_dir)

    @property
    def sample_dir(self) -> Path:
        return _resolve(self.paths.sample_dir)

    @property
    def artifacts_dir(self) -> Path:
        return _resolve(self.paths.artifacts_dir)

    @property
    def models_dir(self) -> Path:
        return self.artifacts_dir / "models"

    def with_overrides(self, **sections: Any) -> Config:
        """Return a copy with top-level fields replaced (used by tests and the sample build)."""
        data = self.model_dump()
        for key, value in sections.items():
            if isinstance(value, BaseModel):
                value = value.model_dump()
            if isinstance(data.get(key), dict) and isinstance(value, dict):
                data[key] = {**data[key], **value}
            else:
                data[key] = value
        return Config.model_validate(data)


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def load_config(path: Path | str | None = None) -> Config:
    with open(path or DEFAULT_CONFIG_PATH, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Config.model_validate(raw)


@lru_cache(maxsize=1)
def get_config() -> Config:
    return load_config()
