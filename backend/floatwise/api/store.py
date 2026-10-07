"""In-memory data access for the API: data, forecasts, models and cached artifacts (loaded once).

Forecasts are precomputed (artifacts/forecasts.parquet) so every request is a few array lookups.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from floatwise.api.persistence import Conflict, OperationsDB
from floatwise.config import Config
from floatwise.data.calendar_bd import upcoming_events
from floatwise.data.generate import load_dataset
from floatwise.engine.allocate import PLANNERS
from floatwise.engine.recommend import PolicyParams, reason_codes, recommend, risk_band
from floatwise.explain import llm, templates
from floatwise.explain.shap_explain import explain_row
from floatwise.features.build import build_panel, to_matrices
from floatwise.models.predict import QuantileModels
from floatwise.simulation.backtest import load_inputs, simulate

Q_COLS = ["cashout_p10", "cashout_p50", "cashout_p90", "cashin_p10", "cashin_p50", "cashin_p90"]


class DateOutOfRange(ValueError):
    pass


class UnknownId(KeyError):
    pass


def _read_json(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class Store:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.data = load_dataset(cfg.data_dir)
        self.agents = self.data["agents"].sort_values("agent_id").reset_index(drop=True)
        self.agent_pos = {a: i for i, a in enumerate(self.agents["agent_id"])}
        self.capacity = self.agents["float_capacity"].to_numpy(dtype=float)
        self.calendar = self.data["calendar"]
        self.cal = self.calendar.set_index("date")
        self.m = to_matrices(self.data["daily"])
        assert list(self.m.agent_ids) == list(self.agents["agent_id"])
        self.date_pos = {d.date(): i for i, d in enumerate(self.m.dates)}

        daily = self.data["daily"].sort_values(["agent_id", "date"])
        shape = (len(self.agents), len(self.m.dates))
        self.close_cash = daily["close_cash"].to_numpy(dtype=float).reshape(shape)
        self.close_efloat = daily["close_efloat"].to_numpy(dtype=float).reshape(shape)

        art = cfg.artifacts_dir
        fc = pd.read_parquet(art / "forecasts.parquet")
        self.origins = sorted(pd.to_datetime(fc["origin"].unique()))
        self.origin_pos = {d.date(): i for i, d in enumerate(self.origins)}
        H = cfg.model.horizons
        self.F = np.zeros((len(self.origins), len(self.agents), H, 6), dtype=np.float64)
        self.A = np.full((len(self.origins), len(self.agents), H, 2), np.nan)
        oi = fc["origin"].map(lambda d: self.origin_pos[d.date()]).to_numpy()
        ai = fc["agent_id"].map(self.agent_pos).to_numpy()
        hi = fc["horizon"].to_numpy().astype(int) - 1
        self.F[oi, ai, hi] = fc[Q_COLS].to_numpy(dtype=float)
        self.A[oi, ai, hi] = fc[["actual_cashout", "actual_cashin"]].astype("float64").to_numpy()

        self.models = QuantileModels.load(cfg)
        self.metrics = _read_json(art / "metrics.json") or {}
        if self.metrics and self.metrics.get("version") != self.models.version:
            raise ValueError("Forecast/model metrics versions differ; run make evaluate and make simulate")
        self.simulation_default = _read_json(art / "simulation_default.json")
        self.fairness = _read_json(art / "fairness.json")
        self.policy_tuning = _read_json(art / "policy_tuning.json")
        self.narrative_cache: dict = _read_json(art / "narratives_cache.json") or {}
        self.decisions_path = art / "decisions.json"
        self.operations = OperationsDB(art / "operations.sqlite3", self.decisions_path)
        train_end = self.date_pos[cfg.dates.train_end]
        self.training_reference = {}
        for side, values in self.m.y.items():
            prior = pd.DataFrame(values.T).shift(1).rolling(28, min_periods=1).mean().to_numpy().T
            ratios = values[:, 28 : train_end + 1] / np.maximum(prior[:, 28 : train_end + 1], 1000)
            self.training_reference[side] = float(np.mean(ratios))
        self.artifact_model_version = self.models.version
        from floatwise.integration.service import Integration

        self.integration = Integration(self)
        self._lock = threading.Lock()
        self._sim_inputs = None

    # ---- dates ---------------------------------------------------------------
    @property
    def first_date(self) -> dt.date:
        return self.origins[0].date()

    @property
    def last_date(self) -> dt.date:
        return self.origins[-1].date()

    def check_date(self, d: dt.date) -> None:
        if d not in self.origin_pos or d not in self.date_pos:
            raise DateOutOfRange(f"date must be between {self.first_date} and {self.last_date}")

    def agent_index(self, agent_id: str) -> int:
        if agent_id not in self.agent_pos:
            raise UnknownId(f"unknown agent {agent_id}")
        return self.agent_pos[agent_id]

    # ---- recommendations -----------------------------------------------------
    def params(self, service_level: float | None = None) -> PolicyParams:
        return PolicyParams.from_config(self.cfg, service_level=service_level)

    def quantiles(self, d: dt.date, h: int = 1) -> tuple[np.ndarray, np.ndarray]:
        self.integration.sync_model()
        f = self.F[self.origin_pos[d], :, h - 1].copy()
        if self.models.version != self.artifact_model_version:
            full = self._active_predictions(d, self.models.version)
            f = full[:, h - 1].copy()
        for agent, forecast in self.integration.overrides(d).items():
            point = forecast["points"][h - 1]
            f[self.agent_index(agent)] = [
                point[side][q] for side in ("cashout", "cashin") for q in ("p10", "p50", "p90")
            ]
        return f[:, :3], f[:, 3:]

    @lru_cache(maxsize=16)  # noqa: B019
    def _active_predictions(self, d: dt.date, version: str) -> np.ndarray:
        panel = build_panel(self.cfg, self.m, self.calendar, self.agents, np.array([self.date_pos[d]]))
        preds = [self.models.predict_amount(panel, side) for side in ("cashout", "cashin")]
        return np.concatenate(preds, axis=1).reshape(len(self.agents), self.cfg.model.horizons, 6)

    def network_rec(self, d: dt.date, service_level: float | None = None) -> dict:
        self.check_date(d)
        self.integration.sync_model()
        with self.operations.connect() as db:
            rows = db.execute(
                "SELECT agent_id, cash, efloat, version FROM balances WHERE day=?", (str(d),)
            ).fetchall()
        with self.operations.connect() as db:
            integrated = db.execute("SELECT 1 FROM integration_revisions LIMIT 1").fetchone()
        if rows or integrated or self.models.version != self.artifact_model_version:
            t = self.date_pos[d]
            cash, efloat = self.close_cash[:, t].copy(), self.close_efloat[:, t].copy()
            versions = np.zeros(len(self.agents), dtype=int)
            for agent_id, ca, ef, version in rows:
                i = self.agent_index(agent_id)
                cash[i], efloat[i] = ca, ef
                versions[i] = version
            co_q, ci_q = self.quantiles(d)
            rec = recommend(self.params(service_level), cash, efloat, self.capacity, co_q, ci_q)
            rec["observed_cash"], rec["observed_efloat"] = cash, efloat
            rec["balance_version"] = versions
            rec["band"] = risk_band(rec["p_stockout"], self.params(service_level).risk_threshold)
            return rec
        return self._network_rec(d, service_level)

    def balance(self, agent_id: str, d: dt.date) -> dict:
        self.check_date(d)
        i, t = self.agent_index(agent_id), self.date_pos[d]
        return self.operations.balance(agent_id, d) or {
            "version": 0,
            "cash": int(self.close_cash[i, t]),
            "efloat": int(self.close_efloat[i, t]),
        }

    def observe_balance(self, body: dict, actor: str) -> dict:
        self.check_date(body["date"])
        i = self.agent_index(body["agent_id"])
        if body["cash"] + body["efloat"] != int(self.capacity[i]):
            raise ValueError("Cash plus e-float must equal the synthetic agent's float capacity")
        return self.operations.set_balance(
            body["agent_id"], body["date"], body["cash"], body["efloat"], body["expected_version"], actor
        )

    def live_forecast(self, agent_id: str, d: dt.date) -> dict:
        """Execute the loaded boosters using history available at this origin, never forecast artifacts."""
        self.check_date(d)
        self.agent_index(agent_id)
        return self.integration.infer(agent_id, d)

    @lru_cache(maxsize=64)  # noqa: B019 — the store lives for the whole process
    def _network_rec(self, d: dt.date, service_level: float | None) -> dict:
        t = self.date_pos[d]
        co_q, ci_q = self.quantiles(d)
        rec = recommend(
            self.params(service_level),
            self.close_cash[:, t],
            self.close_efloat[:, t],
            self.capacity,
            co_q,
            ci_q,
        )
        rec["band"] = risk_band(rec["p_stockout"], self.params(service_level).risk_threshold)
        rec["observed_cash"] = self.close_cash[:, t]
        rec["observed_efloat"] = self.close_efloat[:, t]
        rec["balance_version"] = np.zeros(len(self.agents), dtype=int)
        return rec

    def agent_summary(self, i: int, rec: dict) -> dict:
        a = self.agents.iloc[i]
        return {
            "agent_id": a["agent_id"], "shop_name": a["shop_name"], "archetype": a["archetype"],
            "division": a["division"], "district": a["district"], "upazila": a["upazila"],
            "lat": float(a["lat"]), "lon": float(a["lon"]), "dso_id": a["dso_id"],
            "distributor_id": a["distributor_id"], "float_capacity": int(a["float_capacity"]),
            "p_stockout": round(float(rec["p_stockout"][i]), 3), "risk_band": str(rec["band"][i]),
            "action": str(rec["action"][i]), "amount": int(rec["amount"][i]),
        }  # fmt: skip

    def list_agents(self, d: dt.date, district=None, archetype=None, dso_id=None, risk_min=0.0) -> list[dict]:
        rec = self.network_rec(d)
        a = self.agents
        mask = rec["p_stockout"] >= risk_min
        if district:
            mask &= (a["district"] == district).to_numpy()
        if archetype:
            mask &= (a["archetype"] == archetype).to_numpy()
        if dso_id:
            mask &= (a["dso_id"] == dso_id).to_numpy()
        return [self.agent_summary(i, rec) for i in np.where(mask)[0]]

    def agent_detail(self, agent_id: str, d: dt.date, days: int = 28) -> dict:
        i = self.agent_index(agent_id)
        rec = self.network_rec(d)
        t = self.date_pos[d]
        lo = max(0, t - days + 1)
        daily = self.data["daily"]
        hist = daily[
            (daily["agent_id"] == agent_id) & daily["date"].between(self.m.dates[lo], self.m.dates[t])
        ]
        history = [
            {
                "date": r.date.date(), "cashout_amt": int(r.cashout_amt), "cashin_amt": int(r.cashin_amt),
                "close_cash": int(r.close_cash), "close_efloat": int(r.close_efloat),
                "stockout_cash": bool(r.stockout_cash), "stockout_efloat": bool(r.stockout_efloat),
            }
            for r in hist.sort_values("date").itertuples()
        ]  # fmt: skip
        _, projected = self.integration.rows(agent_id, d)
        updates = {date: (ci, co, di, do) for date, ci, co, di, do, _ in projected}
        for point in history:
            replacement = updates.get(str(point["date"]))
            if replacement:
                ci, co, di, do = replacement
                point.update(cashin_amt=ci, cashout_amt=co, stockout_efloat=bool(di), stockout_cash=bool(do))
                balance = self.balance(agent_id, point["date"])
                point.update(close_cash=balance["cash"], close_efloat=balance["efloat"])
        return {
            "agent": self.agent_summary(i, rec), "date": d,
            "close_cash": int(rec["observed_cash"][i]), "close_efloat": int(rec["observed_efloat"][i]),
            "history": history,
        }  # fmt: skip

    def forecast(self, agent_id: str, d: dt.date, horizon: int) -> dict:
        i = self.agent_index(agent_id)
        self.check_date(d)
        with self.operations.connect() as db:
            revision = self.integration.revision(db, agent_id)
        self.integration.sync_model()
        if revision or self.models.version != self.artifact_model_version:
            forecast = self.integration.infer(agent_id, d)
            return {**forecast, "points": forecast["points"][:horizon]}
        o = self.origin_pos[d]
        points = []
        for h in range(1, horizon + 1):
            f, act = self.F[o, i, h - 1], self.A[o, i, h - 1]
            points.append({
                "date": d + dt.timedelta(days=h), "horizon": h,
                "cashout": {"p10": int(f[0]), "p50": int(f[1]), "p90": int(f[2])},
                "cashin": {"p10": int(f[3]), "p50": int(f[4]), "p90": int(f[5])},
                "actual_cashout": None if np.isnan(act[0]) else int(act[0]),
                "actual_cashin": None if np.isnan(act[1]) else int(act[1]),
            })  # fmt: skip
        return {
            "agent_id": agent_id,
            "origin": d,
            "points": points,
            "source": "precomputed",
            "model_version": self.artifact_model_version,
            "history_revision": 0,
            "balance_revision": self.balance(agent_id, d)["version"],
            "policy_version": self.integration.policy_version,
        }

    def recommendation(self, agent_id: str, d: dt.date, service_level: float | None = None) -> dict:
        i = self.agent_index(agent_id)
        self.integration.sync_model()
        before_model = self.models.version
        with self.operations.connect() as db:
            before_revision = self.integration.revision(db, agent_id)
        before_balance = self.balance(agent_id, d)["version"]
        rec = self.network_rec(d, service_level)
        params = self.params(service_level)
        t = self.date_pos[d]
        eff = d + dt.timedelta(days=1)

        # 7-day outlook: risk each day if the agent does nothing from tonight's balances
        H = self.cfg.model.horizons
        current = self.forecast(agent_id, d, H)
        f = np.array(
            [
                [p[side][q] for side in ("cashout", "cashin") for q in ("p10", "p50", "p90")]
                for p in current["points"]
            ]
        )
        cash = np.full(H, rec["observed_cash"][i])
        efl = np.full(H, rec["observed_efloat"][i])
        out = recommend(params, cash, efl, np.full(H, self.capacity[i]), f[:, :3], f[:, 3:])
        outlook = [
            {
                "date": d + dt.timedelta(days=h + 1),
                "p_cash_stockout": round(float(out["p_cash_stockout"][h]), 3),
                "p_efloat_stockout": round(float(out["p_efloat_stockout"][h]), 3),
                "cash_need": int(out["target_cash"][h]), "efloat_need": int(out["target_efloat"][h]),
                "at_risk": bool(out["p_stockout"][h] >= params.risk_threshold),
            }
            for h in range(H)
        ]  # fmt: skip
        first_risk = next((o["date"] for o in outlook if o["at_risk"]), None)
        revision, matrix = self.integration.matrix(agent_id, d)
        if (
            before_revision != revision
            or before_balance != self.balance(agent_id, d)["version"]
            or before_model != self.models.version
        ):
            raise Conflict("Operational inputs changed; refresh the recommendation")
        recent = int(
            matrix.stockout["cashout"][0, max(0, t - 6) : t + 1].sum()
            + matrix.stockout["cashin"][0, max(0, t - 6) : t + 1].sum()
        )
        today_row = self.cal.loc[pd.Timestamp(d)]
        eff_row = self.cal.loc[pd.Timestamp(eff)] if pd.Timestamp(eff) in self.cal.index else today_row
        return {
            "agent_id": agent_id, "date": d, "effective_date": eff,
            "action": str(rec["action"][i]), "amount": int(rec["amount"][i]),
            "open_cash": int(rec["observed_cash"][i]), "open_efloat": int(rec["observed_efloat"][i]),
            "cash_target": int(rec["target_cash"][i]), "efloat_target": int(rec["target_efloat"][i]),
            "p_cash_stockout": round(float(rec["p_cash_stockout"][i]), 3),
            "p_efloat_stockout": round(float(rec["p_efloat_stockout"][i]), 3),
            "extra_float_needed": int(rec["extra_float_needed"][i]),
            "service_level": params.service_level,
            "balance_version": int(rec["balance_version"][i]),
            "history_revision": revision,
            "model_version": self.models.version,
            "policy_version": self.integration.policy_version,
            "reason_codes": reason_codes(today_row, eff_row, rec, i, params, recent),
            "outlook": outlook, "first_risk_date": first_risk,
        }  # fmt: skip

    # ---- explanation -----------------------------------------------------------
    @lru_cache(maxsize=16)  # noqa: B019
    def _panel_at(self, d: dt.date) -> pd.DataFrame:
        t = self.date_pos[d]
        return build_panel(
            self.cfg, self.m, self.calendar, self.agents, np.array([t]), horizons=np.array([1])
        )

    def warm_up(self, d: dt.date) -> None:
        """Precompute the network recommendation and SHAP feature panel for one date."""
        if d in self.origin_pos and d in self.date_pos:
            self.network_rec(d)
            self._panel_at(d)

    def next_event(self, d: dt.date) -> tuple[str, dt.date, int] | None:
        evs = [
            e for e in upcoming_events(self.cfg, d, within_days=14) if e[0] != "Salary window" and e[2] >= 1
        ]
        return evs[0] if evs else None

    def explanation(self, agent_id: str, d: dt.date, lang: str) -> dict:
        i = self.agent_index(agent_id)
        rec = self.recommendation(agent_id, d)
        target = "cashin" if rec["action"] == "TOP_UP_EFLOAT" else "cashout"
        _, matrix = self.integration.matrix(agent_id, d)
        row = build_panel(
            self.cfg, matrix, self.calendar, self.agents, np.array([self.date_pos[d]]), horizons=np.array([1])
        )
        ex = explain_row(self.cfg, self.models, row, target, lang)
        co_q, ci_q = self.quantiles(d)
        q = ci_q[i] if target == "cashin" else co_q[i]
        facts_rec = {**rec, "p_stockout": max(rec["p_cash_stockout"], rec["p_efloat_stockout"]),
                     "demand_p50": q[1], "demand_p90": q[2]}  # fmt: skip
        agent = self.agents.iloc[i].to_dict()
        facts = templates.facts(facts_rec, agent, ex["drivers"], self.next_event(d), lang)
        narrative, source = self.narrative(agent_id, d, lang, facts)
        return {"agent_id": agent_id, "date": d, "lang": lang, **ex, "narrative": narrative, "source": source}

    @staticmethod
    def narrative_key(agent_id: str, d: dt.date, lang: str, facts: dict) -> str:
        digest = hashlib.sha1(json.dumps(facts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]
        return f"{agent_id}|{d}|{lang}|{digest}"

    def narrative(self, agent_id: str, d: dt.date, lang: str, facts: dict) -> tuple[str, str]:
        key = self.narrative_key(agent_id, d, lang, facts)
        hit = self.narrative_cache.get(key)
        if hit:
            return hit["text"], "cache"
        res = llm.generate(self.cfg, facts, lang)
        if res.source == "llm":
            self.narrative_cache[key] = {"text": res.text, "source": "llm"}
        return res.text, res.source

    # ---- DSO plan & network ------------------------------------------------------
    def dso_ids(self) -> list[str]:
        return sorted(self.agents["dso_id"].unique())

    def dsos(self, d: dt.date) -> list[dict]:
        rec = self.network_rec(d)
        out = []
        for dso, g in self.agents.groupby("dso_id"):
            idx = g.index.to_numpy()
            out.append({"dso_id": dso, "district": g["district"].mode().iloc[0], "n_agents": len(idx),
                        "n_at_risk": int((rec["action"][idx] != "NO_ACTION").sum())})  # fmt: skip
        return out

    def dso_plan(self, dso_id: str, d: dt.date, max_visits: int | None, max_cash: int | None) -> dict:
        if dso_id not in set(self.agents["dso_id"]):
            raise UnknownId(f"unknown DSO {dso_id}")
        rec = self.network_rec(d)
        k = self.cfg.policy.dso.max_visits if max_visits is None else max_visits
        mc = self.cfg.policy.dso.max_cash if max_cash is None else max_cash
        idx = self.agents.index[self.agents["dso_id"] == dso_id].to_numpy()
        plan = PLANNERS[self.cfg.policy.dso.allocator](
            rec["action"][idx], rec["cash_delta"][idx], rec["expected_shortfall"][idx], k, mc
        )
        a = self.agents

        def base(j: int) -> dict:
            i = idx[j]
            return {"agent_id": a.at[i, "agent_id"], "shop_name": a.at[i, "shop_name"],
                    "action": str(rec["action"][i]), "amount": int(rec["amount"][i]),
                    "p_stockout": round(float(rec["p_stockout"][i]), 3),
                    "priority_bdt": int(round(rec["expected_shortfall"][i]))}  # fmt: skip

        visits = [
            {**base(j), "rank": r + 1, "upazila": a.at[idx[j], "upazila"],
             "lat": float(a.at[idx[j], "lat"]), "lon": float(a.at[idx[j], "lon"])}
            for r, j in enumerate(plan.visits)
        ]  # fmt: skip
        excluded = [{**base(j), "reason": reason} for j, reason in plan.excluded]
        return {"dso_id": dso_id, "date": d, "max_visits": k, "max_cash": mc, "cash_to_carry": plan.cash_to_carry,
                "efloat_to_send": plan.efloat_to_send, "visits": visits, "excluded": excluded}  # fmt: skip

    def network_summary(self, d: dt.date) -> dict:
        rec = self.network_rec(d)
        a = self.agents
        cash = np.where(rec["action"] == "TOP_UP_CASH", rec["amount"], 0)
        efl = np.where(rec["action"] == "TOP_UP_EFLOAT", rec["amount"], 0)
        by_district = []
        for district, g in a.groupby("district"):
            idx = g.index.to_numpy()
            by_district.append({
                "district": district, "n_agents": len(idx),
                "n_high": int((rec["band"][idx] == "high").sum()),
                "n_medium": int((rec["band"][idx] == "medium").sum()),
                "recommended_cash": int(cash[idx].sum()), "recommended_efloat": int(efl[idx].sum()),
            })  # fmt: skip
        bands, counts = np.unique(rec["band"], return_counts=True)
        acts, acounts = np.unique(rec["action"].astype(str), return_counts=True)
        return {
            "date": d, "n_agents": len(a),
            "by_band": {"low": 0, "medium": 0, "high": 0} | {str(b): int(c) for b, c in zip(bands, counts, strict=True)},
            "by_action": {str(x): int(c) for x, c in zip(acts, acounts, strict=True)},
            "recommended_cash": int(cash.sum()), "recommended_efloat": int(efl.sum()),
            "by_district": sorted(by_district, key=lambda r: -(r["n_high"] * 10 + r["n_medium"])),
            "upcoming_events": [{"name": n, "date": e, "days_to": k}
                                for n, e, k in upcoming_events(self.cfg, d, within_days=45)],
        }  # fmt: skip

    # ---- simulation ---------------------------------------------------------------
    def simulate(self, req: dict) -> dict:
        start = req.get("start") or self.cfg.dates.test_start
        end = req.get("end") or self.cfg.dates.test_end
        if start < self.cfg.dates.val_start or end > self.cfg.dates.test_end or start > end:
            raise DateOutOfRange(f"simulation range must be within {self.cfg.dates.val_start} and "
                                 f"{self.cfg.dates.test_end}")  # fmt: skip
        default = (start, end) == (self.cfg.dates.test_start, self.cfg.dates.test_end) and all(
            req.get(k) is None
            for k in ("service_level", "risk_threshold", "overlap_alpha", "max_visits", "max_cash")
        )
        if default and self.simulation_default is not None:
            return {**self.simulation_default, "source": "cache"}
        with self._lock:
            key = (start, end)
            if self._sim_inputs is None or self._sim_inputs[0] != key:
                fc = pd.read_parquet(self.cfg.artifacts_dir / "forecasts.parquet")
                self._sim_inputs = (key, load_inputs(self.cfg, self.data, fc, start, end))
            inp = self._sim_inputs[1]
        params = PolicyParams.from_config(self.cfg, service_level=req.get("service_level"),
                                          risk_threshold=req.get("risk_threshold"),
                                          overlap_alpha=req.get("overlap_alpha"))  # fmt: skip
        res = simulate(self.cfg, inp, params, req.get("max_visits"), req.get("max_cash"))
        return {**res, "source": "live"}

    # ---- decisions (human in the loop) ------------------------------------------------
    def add_decision(self, decision: dict, actor: str = "local-demo", idem: str | None = None) -> dict:
        self.agent_index(decision["agent_id"])
        return self.operations.add_decision(decision, actor, idem)

    def list_decisions(self) -> list[dict]:
        return self.operations.decisions()

    def decision_summary(self, items: list[dict] | None = None) -> dict:
        """Aggregate human decisions into a feedback signal for retraining (FR-HITL-3)."""
        items = self.list_decisions() if items is None else items
        by_decision = {"approve": 0, "modify": 0, "reject": 0}
        by_action: dict[str, int] = {}
        reasons: dict[str, int] = {}
        changes = []
        for d in items:
            by_decision[d["decision"]] = by_decision.get(d["decision"], 0) + 1
            by_action[d["action"]] = by_action.get(d["action"], 0) + 1
            if d["decision"] == "reject":
                key = (d.get("reason") or "").strip().lower() or "(no reason given)"
                reasons[key] = reasons.get(key, 0) + 1
            if d["decision"] == "modify" and d["recommended_amount"] > 0:
                changes.append((d["final_amount"] - d["recommended_amount"]) / d["recommended_amount"])
        total = len(items)
        return {
            "total": total,
            "by_decision": by_decision,
            "by_action": by_action,
            "approval_rate": round(by_decision["approve"] / total, 3) if total else 0.0,
            "avg_modify_change_pct": round(100 * sum(changes) / len(changes), 1) if changes else None,
            "recommended_bdt": int(sum(d["recommended_amount"] for d in items)),
            "final_bdt": int(sum(d["final_amount"] for d in items)),
            "top_rejection_reasons": [
                {"reason": r, "count": c} for r, c in sorted(reasons.items(), key=lambda x: (-x[1], x[0]))[:5]
            ],
        }
