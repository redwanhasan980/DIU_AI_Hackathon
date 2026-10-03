"""Synthetic agent network (FR-DATA-1). No real people or businesses (R-DATA-1, R-DATA-2)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from floatwise.config import Config


def _archetype_counts(cfg: Config, n: int) -> dict[str, int]:
    shares = cfg.network.archetype_share
    counts = {a: int(np.floor(s * n)) for a, s in shares.items()}
    # hand the rounding remainder to the largest archetypes, deterministically
    for a in sorted(shares, key=lambda k: -shares[k])[: n - sum(counts.values())]:
        counts[a] += 1
    return counts


def build_agents(cfg: Config, rng: np.random.Generator) -> pd.DataFrame:
    net = cfg.network
    rows = []
    for archetype, count in _archetype_counts(cfg, net.n_agents).items():
        weights = net.archetype_districts[archetype]
        names = list(weights)
        p = np.array([weights[k] for k in names], dtype=float)
        districts = rng.choice(names, size=count, p=p / p.sum())
        arch = cfg.archetypes[archetype]
        for district in districts:
            division, lat, lon, upazilas = net.districts[district]
            size = float(rng.lognormal(0.0, net.size_factor_sigma))
            cap_mult = rng.uniform(*net.float_capacity_range)
            capacity = int(round(cap_mult * (arch.base_co + arch.base_ci) * size, -3))
            rows.append(
                {
                    "archetype": archetype,
                    "division": division,
                    "district": district,
                    "upazila": str(rng.choice(upazilas)),
                    "lat": round(lat + rng.uniform(-1, 1) * net.location_jitter_deg, 5),
                    "lon": round(lon + rng.uniform(-1, 1) * net.location_jitter_deg, 5),
                    "size_factor": round(size, 4),
                    "float_capacity": capacity,
                    "onboard_date": dt.date(2019, 1, 1) + dt.timedelta(days=int(rng.integers(0, 1800))),
                    "shop_name": f"{rng.choice(net.shop_prefixes)} {rng.choice(net.shop_suffixes)}",
                }
            )

    agents = pd.DataFrame(rows).sort_values(["district", "upazila", "archetype"], kind="stable")
    agents = agents.reset_index(drop=True)
    agents.insert(0, "agent_id", [f"AG{i + 1:05d}" for i in range(len(agents))])
    agents["dso_id"], agents["distributor_id"] = _assign_dsos(cfg, agents)

    share_co = np.array([cfg.archetypes[a].base_co for a in agents["archetype"]])
    share_ci = np.array([cfg.archetypes[a].base_ci for a in agents["archetype"]])
    cash = np.round(agents["float_capacity"] * share_co / (share_co + share_ci), -3)
    agents["opening_cash"] = cash.astype(int)
    agents["opening_efloat"] = (agents["float_capacity"] - agents["opening_cash"]).astype(int)
    return agents


def _assign_dsos(cfg: Config, agents: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Chunk each district's agents into DSO territories; group DSOs into distributors."""
    per_dso = cfg.network.agents_per_dso
    dso_ids: list[str] = [""] * len(agents)
    dist_ids: list[str] = [""] * len(agents)
    dso_counter = 0
    for _, idx in agents.groupby("district", sort=True).groups.items():
        idx = list(idx)
        n_dsos = max(1, int(np.ceil(len(idx) / per_dso)))
        for chunk in np.array_split(idx, n_dsos):
            dso_counter += 1
            dso = f"DSO{dso_counter:03d}"
            distributor = f"DB{(dso_counter - 1) // cfg.network.dsos_per_distributor + 1:02d}"
            for i in chunk:
                dso_ids[i] = dso
                dist_ids[i] = distributor
    return dso_ids, dist_ids
