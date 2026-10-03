"""Generate the synthetic dataset: `python -m floatwise.data.generate [--sample]` (FR-DATA-1..8)."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from floatwise.config import Config, get_config
from floatwise.data.agents import build_agents
from floatwise.data.calendar_bd import build_calendar
from floatwise.data.demand import build_demand
from floatwise.data.shocks import build_shocks, shock_matrix
from floatwise.data.simulate_status_quo import simulate_status_quo

SAMPLE_AGENTS = 50


def generate(cfg: Config) -> dict[str, pd.DataFrame]:
    seq = np.random.SeedSequence(cfg.seed)
    rng_agents, rng_shocks, rng_demand = (np.random.default_rng(s) for s in seq.spawn(3))

    calendar = build_calendar(cfg)
    agents = build_agents(cfg, rng_agents)
    shocks = build_shocks(cfg, calendar, rng_shocks)
    districts = sorted(cfg.network.districts)
    dates = pd.DatetimeIndex(calendar["date"])
    smat = shock_matrix(shocks, districts, dates)
    demand = build_demand(cfg, agents, calendar, smat, districts, rng_demand)
    ledger = simulate_status_quo(cfg, agents, calendar, demand)

    d_idx = agents["district"].map({d: i for i, d in enumerate(districts)}).to_numpy()
    daily = _to_long(agents, dates, demand, ledger, smat[d_idx] < 1.0)
    return {"agents": agents, "calendar": calendar, "daily": daily, "shocks": shocks}


def _to_long(agents, dates, demand, ledger, shock_flag) -> pd.DataFrame:
    n_a, n_d = demand["co_demand"].shape

    def flat(a: np.ndarray) -> np.ndarray:
        return a.reshape(-1)

    def amt(a: np.ndarray) -> np.ndarray:
        return np.round(flat(a)).astype(np.int64)

    co_dem, ci_dem = amt(demand["co_demand"]), amt(demand["ci_demand"])
    co_srv, ci_srv = amt(ledger["served_co"]), amt(ledger["served_ci"])
    df = pd.DataFrame(
        {
            "agent_id": np.repeat(agents["agent_id"].to_numpy(), n_d),
            "date": np.tile(dates.to_numpy(), n_a),
            "cashout_demand_amt": co_dem,
            "cashin_demand_amt": ci_dem,
            "cashout_amt": co_srv,
            "cashin_amt": ci_srv,
            "cashout_cnt": np.round(flat(ledger["served_co"] / demand["co_ticket"])).astype(np.int64),
            "cashin_cnt": np.round(flat(ledger["served_ci"] / demand["ci_ticket"])).astype(np.int64),
            "unserved_cashout_amt": co_dem - co_srv,
            "unserved_cashin_amt": ci_dem - ci_srv,
            "open_cash": amt(ledger["open_cash"]),
            "open_efloat": amt(ledger["open_efloat"]),
            "close_cash": amt(ledger["close_cash"]),
            "close_efloat": amt(ledger["close_efloat"]),
            "stockout_cash": flat(demand["co_demand"] - ledger["served_co"]) > 1.0,
            "stockout_efloat": flat(demand["ci_demand"] - ledger["served_ci"]) > 1.0,
            "rebalance_cash_amt": amt(ledger["rebalance_cash"]),
            "shock_flag": flat(shock_flag),
        }
    )
    df["agent_id"] = df["agent_id"].astype(str)
    return df


def write_dataset(data: dict[str, pd.DataFrame], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    data["agents"].to_csv(out_dir / "agents.csv", index=False)
    data["calendar"].to_csv(out_dir / "calendar.csv", index=False)
    data["shocks"].to_csv(out_dir / "shocks.csv", index=False)
    data["daily"].to_parquet(out_dir / "daily.parquet", index=False, compression="zstd")


def load_dataset(data_dir: Path) -> dict[str, pd.DataFrame]:
    agents = pd.read_csv(data_dir / "agents.csv", dtype={"agent_id": str})
    calendar = pd.read_csv(data_dir / "calendar.csv", parse_dates=["date"])
    calendar["event_name"] = calendar["event_name"].fillna("")
    shocks = pd.read_csv(data_dir / "shocks.csv", parse_dates=["start_date", "end_date"])
    daily = pd.read_parquet(data_dir / "daily.parquet")
    daily["date"] = pd.to_datetime(daily["date"])
    return {"agents": agents, "calendar": calendar, "daily": daily, "shocks": shocks}


def summarize(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    d = data["daily"].merge(data["agents"][["agent_id", "archetype"]], on="agent_id")
    return (
        d.groupby("archetype")
        .agg(
            agents=("agent_id", "nunique"),
            mean_cashout=("cashout_demand_amt", "mean"),
            mean_cashin=("cashin_demand_amt", "mean"),
            cash_stockout_rate=("stockout_cash", "mean"),
            efloat_stockout_rate=("stockout_efloat", "mean"),
        )
        .round(3)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="store_true", help=f"write a {SAMPLE_AGENTS}-agent sample")
    args = parser.parse_args()

    cfg = get_config()
    out_dir = cfg.data_dir
    if args.sample:
        cfg = cfg.with_overrides(network={"n_agents": SAMPLE_AGENTS})
        out_dir = cfg.sample_dir
    t0 = time.time()
    data = generate(cfg)
    write_dataset(data, out_dir)
    print(
        f"wrote {len(data['daily']):,} agent-days for {len(data['agents'])} agents to {out_dir} "
        f"in {time.time() - t0:.1f}s"
    )
    print(summarize(data).to_string())


if __name__ == "__main__":
    main()
