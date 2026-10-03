"""Bangladesh event calendar (FR-DATA-2): Eid, Ramadan, salary window, Boishakh, holidays."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from floatwise.config import CalendarCfg, Config

CLIP_DAYS = 60  # "far from any Eid" — distances are clipped so the model sees a stable value


def _day_numbers(values) -> np.ndarray:
    """Dates -> integer day numbers (unit-safe across pandas datetime resolutions)."""
    return np.asarray(values, dtype="datetime64[D]").astype(np.int64)


def _days_to_next(dates: pd.DatetimeIndex, events: list[dt.date]) -> np.ndarray:
    """Days until the next event on or after each date (0 on the event day), clipped."""
    ev = np.sort(_day_numbers(events))
    d = _day_numbers(dates)
    idx = np.searchsorted(ev, d, side="left")
    out = np.full(len(d), CLIP_DAYS, dtype=np.int64)
    has = idx < len(ev)
    out[has] = ev[idx[has]] - d[has]
    return np.minimum(out, CLIP_DAYS)


def _days_since_last(dates: pd.DatetimeIndex, events: list[dt.date]) -> np.ndarray:
    """Days since the most recent event on or before each date (0 on the event day), clipped."""
    ev = np.sort(_day_numbers(events))
    d = _day_numbers(dates)
    idx = np.searchsorted(ev, d, side="right") - 1
    out = np.full(len(d), CLIP_DAYS, dtype=np.int64)
    has = idx >= 0
    out[has] = d[has] - ev[idx[has]]
    return np.minimum(out, CLIP_DAYS)


def _g2p_day_index(dates: pd.DatetimeIndex, cal: CalendarCfg) -> np.ndarray:
    years = range(dates[0].year - 1, dates[-1].year + 1)
    starts = [dt.date(y, int(md[:2]), int(md[3:])) for y in years for md in cal.g2p_disbursement_days]
    since = _days_since_last(dates, starts)
    return np.where(since < len(cal.g2p_curve), since, -1)


def _mmdd_mask(dates: pd.DatetimeIndex, mmdd: list[str]) -> np.ndarray:
    keys = dates.strftime("%m-%d")
    return np.isin(np.asarray(keys), mmdd)


def build_calendar(cfg: Config) -> pd.DataFrame:
    cal: CalendarCfg = cfg.calendar
    dates = pd.date_range(cfg.dates.start, cfg.dates.end, freq="D")
    df = pd.DataFrame({"date": dates})
    df["dow"] = dates.dayofweek.astype(int)
    df["month"] = dates.month.astype(int)
    df["day_of_month"] = dates.day.astype(int)
    df["is_friday"] = df["dow"] == 4
    df["is_saturday"] = df["dow"] == 5
    df["is_weekend"] = df["dow"].isin(cal.weekend_dows)

    df["days_to_eid_fitr"] = _days_to_next(dates, cal.eid_fitr)
    df["days_to_eid_adha"] = _days_to_next(dates, cal.eid_adha)
    df["is_eid_fitr"] = df["days_to_eid_fitr"] == 0
    df["is_eid_adha"] = df["days_to_eid_adha"] == 0
    df["days_after_eid"] = _days_since_last(dates, list(cal.eid_fitr) + list(cal.eid_adha))
    df["is_eid_holiday"] = df["days_after_eid"] < cal.eid_holiday_days

    # Ramadan: the `ramadan_days` days immediately before Eid-ul-Fitr
    df["is_ramadan"] = (df["days_to_eid_fitr"] >= 1) & (df["days_to_eid_fitr"] <= cal.ramadan_days)

    lo, hi = cal.salary_window
    df["is_salary_window"] = (df["day_of_month"] >= lo) & (df["day_of_month"] <= hi)

    # G2P allowance disbursement: day index 0..len(curve)-1 after a scheduled disbursement day, else -1
    df["g2p_day_index"] = _g2p_day_index(dates, cal)
    df["is_g2p_window"] = df["g2p_day_index"] >= 0

    boishakh = [f"{cal.boishakh[:2]}-{int(cal.boishakh[3:]) - k:02d}" for k in range(cal.boishakh_window)]
    df["is_boishakh"] = _mmdd_mask(dates, boishakh)
    df["is_public_holiday"] = _mmdd_mask(dates, cal.public_holidays)

    df["event_name"] = _event_names(df)
    return df


def _event_names(df: pd.DataFrame) -> pd.Series:
    names = np.full(len(df), "", dtype=object)
    names[df["is_salary_window"].to_numpy()] = "Salary window"
    names[df["is_g2p_window"].to_numpy()] = "Allowance disbursement"
    names[df["is_boishakh"].to_numpy()] = "Pohela Boishakh"
    names[df["is_public_holiday"].to_numpy()] = "Public holiday"
    names[df["is_ramadan"].to_numpy()] = "Ramadan"
    pre_fitr = df["days_to_eid_fitr"].between(1, 10).to_numpy()
    pre_adha = df["days_to_eid_adha"].between(1, 10).to_numpy()
    names[pre_fitr] = "Pre Eid-ul-Fitr"
    names[pre_adha] = "Pre Eid-ul-Adha"
    names[df["is_eid_holiday"].to_numpy()] = "Eid holiday"
    names[df["is_eid_fitr"].to_numpy()] = "Eid-ul-Fitr"
    names[df["is_eid_adha"].to_numpy()] = "Eid-ul-Adha"
    return pd.Series(names, index=df.index, dtype=str)


def upcoming_events(cfg: Config, on: dt.date, within_days: int = 45) -> list[tuple[str, dt.date, int]]:
    """Named events (Eid, Boishakh, salary window start) within `within_days` after `on`."""
    cal = cfg.calendar
    out: list[tuple[str, dt.date, int]] = []
    for name, dates in (("Eid-ul-Fitr", cal.eid_fitr), ("Eid-ul-Adha", cal.eid_adha)):
        for d in dates:
            delta = (d - on).days
            if 0 <= delta <= within_days:
                out.append((name, d, delta))
    for year in (on.year, on.year + 1):
        b = dt.date(year, int(cal.boishakh[:2]), int(cal.boishakh[3:]))
        if 0 <= (b - on).days <= within_days:
            out.append(("Pohela Boishakh", b, (b - on).days))
    for year in (on.year, on.year + 1):
        for md in cal.g2p_disbursement_days:
            g = dt.date(year, int(md[:2]), int(md[3:]))
            if 0 <= (g - on).days <= within_days:
                out.append(("Allowance disbursement", g, (g - on).days))
    nxt = (on.replace(day=1) + dt.timedelta(days=32)).replace(day=cal.salary_window[0])
    if on.day < cal.salary_window[0]:
        nxt = on.replace(day=cal.salary_window[0])
    if 0 <= (nxt - on).days <= within_days:
        out.append(("Salary window", nxt, (nxt - on).days))
    return sorted(out, key=lambda e: e[2])
