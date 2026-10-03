"""Visual checks that the injected synthetic patterns exist (FR-DATA-7).

Writes artifacts/plots/{eid_spike,salary_cycle,stockouts_by_event}.png. Run after `make data`:
    python scripts/plot_data_checks.py
Colours: the validated categorical palette in fixed order (dataviz reference instance).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from floatwise.config import get_config  # noqa: E402
from floatwise.data.generate import load_dataset  # noqa: E402

SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]  # categorical slots 1-5, fixed order
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
LABELS = {
    "urban_residential": "Urban residential",
    "garment_belt": "Garment belt",
    "rural_remittance": "Rural remittance",
    "market_hub": "Market hub",
    "university_area": "University area",
}


def _style(ax, title: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold", pad=12)
    ax.set_ylabel(ylabel, color=INK2, fontsize=10)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors=MUTED, labelsize=9, length=0)


def _legend(ax, loc: str = "upper left") -> None:
    leg = ax.legend(frameon=False, fontsize=9, loc=loc)
    for text in leg.get_texts():
        text.set_color(INK2)  # legend text wears ink, the swatch carries identity


def eid_spike(cfg, df: pd.DataFrame, out) -> None:
    eid = pd.Timestamp(cfg.calendar.eid_fitr[1])  # Eid-ul-Fitr 2025
    win = df[(df["date"] >= eid - pd.Timedelta(days=20)) & (df["date"] <= eid + pd.Timedelta(days=10))].copy()
    win["day"] = (win["date"] - eid).dt.days
    base = df[(df["date"] >= eid - pd.Timedelta(days=50)) & (df["date"] < eid - pd.Timedelta(days=20))]
    base = base.groupby("archetype")["cashout_demand_amt"].mean()
    fig, ax = plt.subplots(figsize=(9, 4.2), facecolor=SURFACE)
    for color, (arch, label) in zip(SLOTS, LABELS.items(), strict=True):
        s = win[win["archetype"] == arch].groupby("day")["cashout_demand_amt"].mean() / base[arch]
        ax.plot(s.index, s.values, color=color, linewidth=2, label=label)
    ax.axvline(0, color=MUTED, linestyle="--", linewidth=1)
    ax.text(0.3, ax.get_ylim()[1] * 0.97, "Eid-ul-Fitr 2025", color=MUTED, fontsize=9, va="top")
    _style(ax, "Cash-out demand around Eid-ul-Fitr (× normal level)", "× normal daily cash-out")
    ax.set_xlabel("days relative to Eid", color=INK2, fontsize=10)
    _legend(ax)
    fig.tight_layout()
    fig.savefig(out / "eid_spike.png", dpi=150)
    plt.close(fig)


def salary_cycle(cfg, df: pd.DataFrame, cal: pd.DataFrame, out) -> None:
    calm = cal.loc[cal["event_name"].isin(["", "Salary window"]), "date"]  # exclude Eid/Ramadan
    d = df[df["date"].isin(calm)].copy()
    d["dom"] = d["date"].dt.day
    fig, ax = plt.subplots(figsize=(9, 4.2), facecolor=SURFACE)
    for color, (arch, label) in zip(SLOTS, LABELS.items(), strict=True):
        a = d[d["archetype"] == arch]
        s = a.groupby("dom")["cashout_demand_amt"].mean() / a["cashout_demand_amt"].mean()
        ax.plot(s.index, s.values, color=color, linewidth=2, label=label)
    lo, hi = cfg.calendar.salary_window
    ax.axvspan(lo - 0.5, hi + 0.5, color=GRID, alpha=0.5, linewidth=0)
    ax.text(lo, ax.get_ylim()[1] * 0.98, "salary window", color=MUTED, fontsize=9, va="top")
    _style(ax, "Cash-out by day of month (× monthly average, non-event days)", "× monthly average")
    ax.set_xlabel("day of month", color=INK2, fontsize=10)
    _legend(ax, "upper right")
    fig.tight_layout()
    fig.savefig(out / "salary_cycle.png", dpi=150)
    plt.close(fig)


def stockouts_by_event(df: pd.DataFrame, cal: pd.DataFrame, out) -> None:
    d = df.merge(cal[["date", "event_name"]], on="date")
    d["event"] = d["event_name"].replace("", "Normal day")
    d["stockout"] = d["stockout_cash"] | d["stockout_efloat"]
    rate = d.groupby("event")["stockout"].mean().sort_values()
    fig, ax = plt.subplots(figsize=(9, 4.2), facecolor=SURFACE)
    bars = ax.barh(rate.index, rate.values * 100, color=SLOTS[1], height=0.55)
    for b, v in zip(bars, rate.values, strict=True):
        ax.text(b.get_width() + 0.5, b.get_y() + b.get_height() / 2, f"{v:.0%}", va="center", color=INK2, fontsize=9)
    _style(ax, "Status-quo stockout rate by calendar event (share of agent-days)", "")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("% of agent-days with a cash or e-float stockout", color=INK2, fontsize=10)
    ax.tick_params(axis="y", colors=INK2)
    fig.tight_layout()
    fig.savefig(out / "stockouts_by_event.png", dpi=150)
    plt.close(fig)


def main() -> None:
    cfg = get_config()
    data = load_dataset(cfg.data_dir)
    df = data["daily"].merge(data["agents"][["agent_id", "archetype"]], on="agent_id")
    out = cfg.artifacts_dir / "plots"
    out.mkdir(parents=True, exist_ok=True)
    eid_spike(cfg, df, out)
    salary_cycle(cfg, df, data["calendar"], out)
    stockouts_by_event(df, data["calendar"], out)
    print(f"wrote 3 plots to {out}")


if __name__ == "__main__":
    main()
