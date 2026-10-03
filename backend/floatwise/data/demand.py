"""True daily cash-out / cash-in demand per agent (FR-DATA-3, SRS §5.3).

demand(agent, d) = base[arch] x size[agent] x dow x salary x g2p x eid x ramadan x boishakh x holiday
                   x shock(district, d) x trend(d) x noise
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from floatwise.config import ArchetypeCfg, Config


def archetype_multipliers(cfg: Config, calendar: pd.DataFrame, arch: ArchetypeCfg, side: str) -> np.ndarray:
    """Deterministic calendar multiplier for one archetype and side ('co' or 'ci'), shape (n_dates,)."""
    cal = cfg.calendar
    n = len(calendar)
    m = np.asarray(arch.dow)[calendar["dow"].to_numpy()].astype(float)

    dom = calendar["day_of_month"].to_numpy()
    in_window = calendar["is_salary_window"].to_numpy()
    curve = np.zeros(n)
    curve[in_window] = np.asarray(cal.salary_curve)[dom[in_window] - cal.salary_window[0]]
    m *= 1.0 + getattr(arch.salary_amp, side) * curve

    g2p = calendar["g2p_day_index"].to_numpy()
    g2p_curve = np.zeros(n)
    g2p_curve[g2p >= 0] = np.asarray(cal.g2p_curve)[g2p[g2p >= 0]]
    m *= 1.0 + getattr(arch.g2p_amp, side) * g2p_curve

    ramp = np.asarray(cal.pre_eid_ramp)
    for col, amp in (("days_to_eid_fitr", arch.eid_fitr_amp), ("days_to_eid_adha", arch.eid_adha_amp)):
        k = calendar[col].to_numpy()
        pre = (k >= 1) & (k <= cal.pre_eid_window)
        bump = np.zeros(n)
        bump[pre] = ramp[k[pre] - 1]
        m *= 1.0 + getattr(amp, side) * bump

    after = calendar["days_after_eid"].to_numpy()
    m[after < cal.eid_holiday_days] *= arch.eid_holiday_mult
    post = (after >= cal.eid_holiday_days) & (after < cal.eid_holiday_days + cal.post_eid_days)
    m[post] *= arch.post_eid_mult

    m[calendar["is_ramadan"].to_numpy()] *= getattr(arch.ramadan_mult, side)
    m[calendar["is_boishakh"].to_numpy()] *= arch.boishakh_mult
    m[calendar["is_public_holiday"].to_numpy()] *= arch.holiday_mult
    return m


def build_demand(
    cfg: Config,
    agents: pd.DataFrame,
    calendar: pd.DataFrame,
    shock_mat: np.ndarray,
    districts: list[str],
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Return (n_agents, n_dates) arrays: co_demand, ci_demand, co_ticket, ci_ticket."""
    dates = pd.DatetimeIndex(calendar["date"])
    n_a, n_d = len(agents), len(dates)
    years = (dates - dates[0]).days.to_numpy() / 365.25
    trend = (1.0 + cfg.demand.annual_growth) ** years

    arch_names = list(cfg.archetypes)
    mult = {
        side: np.stack([archetype_multipliers(cfg, calendar, cfg.archetypes[a], side) for a in arch_names])
        for side in ("co", "ci")
    }
    a_idx = agents["archetype"].map({a: i for i, a in enumerate(arch_names)}).to_numpy()
    d_idx = agents["district"].map({d: i for i, d in enumerate(districts)}).to_numpy()
    size = agents["size_factor"].to_numpy()[:, None]
    sigma = np.array([cfg.archetypes[a].noise_sigma for a in agents["archetype"]])[:, None]

    rho = cfg.demand.co_ci_noise_corr
    z1 = rng.standard_normal((n_a, n_d))
    z2 = rho * z1 + np.sqrt(1 - rho**2) * rng.standard_normal((n_a, n_d))
    # mean-one log-normal noise
    noise_co = np.exp(sigma * z1 - sigma**2 / 2)
    noise_ci = np.exp(sigma * z2 - sigma**2 / 2)

    base_co = np.array([cfg.archetypes[a].base_co for a in agents["archetype"]])[:, None]
    base_ci = np.array([cfg.archetypes[a].base_ci for a in agents["archetype"]])[:, None]
    common = size * shock_mat[d_idx] * trend[None, :]
    co = base_co * mult["co"][a_idx] * common * noise_co
    ci = base_ci * mult["ci"][a_idx] * common * noise_ci

    ticket = np.array([cfg.archetypes[a].ticket for a in agents["archetype"]])[:, None]
    ts = cfg.demand.ticket_noise_sigma
    co_ticket = ticket * rng.lognormal(0.0, ts, (n_a, n_d))
    ci_ticket = ticket * rng.lognormal(0.0, ts, (n_a, n_d))
    return {"co_demand": co, "ci_demand": ci, "co_ticket": co_ticket, "ci_ticket": ci_ticket}
