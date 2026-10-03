import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { ActionBadge, AssumptionTag, Card, ErrorBox, Kpi, Loading } from "../components/ui";
import { num, pct, taka, takaShort } from "../lib/format";
import { useApi, useApp } from "../lib/state";

export function DsoPlanPage() {
  const { date, lang, t } = useApp();
  const [params, setParams] = useSearchParams();
  const dsos = useApi(() => api.dsos(date), [date]);
  const busiest = dsos.data ? [...dsos.data].sort((a, b) => b.n_at_risk - a.n_at_risk)[0]?.dso_id : undefined;
  const dso = params.get("dso") ?? busiest ?? "";
  const [maxVisits, setMaxVisits] = useState(10);
  const [maxCash, setMaxCash] = useState(1_000_000);
  const plan = useApi(() => (dso ? api.dsoPlan(dso, date, maxVisits, maxCash) : Promise.resolve(null)), [dso, date, maxVisits, maxCash]);

  if (dsos.error) return <ErrorBox message={dsos.error} />;
  if (!dsos.data) return <Loading text={t.loading} />;
  const p = plan.data;
  const input = "tabular w-28 rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink";

  return (
    <div className="space-y-4">
      <Card
        title={t.dsoTitle}
        subtitle={lang === "bn" ? "টাকার ঝুঁকি অনুযায়ী অগ্রাধিকার; ক্ষমতার সীমার মধ্যে।" : "Highest taka-at-risk first, within the DSO's visit and cash-bag limits."}
        right={
          <div className="flex flex-wrap items-center gap-3 text-sm text-ink-2">
            <select aria-label="DSO" value={dso} onChange={(e) => setParams({ dso: e.target.value })}
              className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink">
              {dsos.data.map((d) => (
                <option key={d.dso_id} value={d.dso_id}>{d.dso_id} · {d.district} ({d.n_at_risk}/{d.n_agents})</option>
              ))}
            </select>
            <label className="flex items-center gap-1">{t.maxVisits}<AssumptionTag />
              <input type="number" min={0} max={50} value={maxVisits} onChange={(e) => setMaxVisits(Number(e.target.value))} className={input} />
            </label>
            <label className="flex items-center gap-1">{t.maxCash} ৳<AssumptionTag />
              <input type="number" min={0} step={50000} value={maxCash} onChange={(e) => setMaxCash(Number(e.target.value))} className={input} />
            </label>
          </div>
        }
      >
        {plan.error && <ErrorBox message={plan.error} />}
        {!p && !plan.error && <Loading text={t.loading} />}
        {p && (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Kpi label={t.visits} value={`${num(p.visits.length, lang)} / ${num(p.max_visits, lang)}`} />
              <Kpi label={t.cashToCarry} value={takaShort(p.cash_to_carry, lang)} sub={`${pct(p.cash_to_carry / Math.max(p.max_cash, 1), lang)} ${lang === "bn" ? "ব্যাগ ব্যবহৃত" : "of bag"}`} />
              <Kpi label={t.efloatToSend} value={takaShort(p.efloat_to_send, lang)} />
              <Kpi label={t.priority} value={takaShort(p.visits.reduce((s, v) => s + v.priority_bdt, 0), lang)}
                sub={lang === "bn" ? "এই রুটে প্রত্যাশিত ঘাটতি" : "expected shortfall covered by this route"} />
            </div>
            <ol className="mt-4 divide-y divide-line">
              {p.visits.map((v) => (
                <li key={v.agent_id} className="flex flex-wrap items-center gap-3 py-2.5">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-sm font-semibold text-white">{v.rank}</span>
                  <div className="min-w-48 flex-1">
                    <Link to={`/agents/${v.agent_id}`} className="font-medium hover:underline">{v.shop_name}</Link>
                    <div className="text-xs text-muted">{v.agent_id} · {v.upazila}</div>
                  </div>
                  <ActionBadge action={v.action} lang={lang} />
                  <span className="tabular w-28 text-right font-medium">{taka(v.amount, lang)}</span>
                  <span className="tabular w-36 text-right text-xs text-ink-2">{t.priority}: {taka(v.priority_bdt, lang)}</span>
                </li>
              ))}
              {p.visits.length === 0 && <li className="py-6 text-center text-sm text-muted">{t.noData}</li>}
            </ol>
          </>
        )}
      </Card>
      {p && p.excluded.length > 0 && (
        <Card title={`${t.excluded} · ${num(p.excluded.length, lang)}`}>
          <ul className="divide-y divide-line text-sm">
            {p.excluded.map((x) => (
              <li key={x.agent_id} className="flex flex-wrap items-center gap-3 py-2">
                <Link to={`/agents/${x.agent_id}`} className="min-w-48 flex-1 hover:underline">{x.shop_name} <span className="text-xs text-muted">{x.agent_id}</span></Link>
                <ActionBadge action={x.action} lang={lang} />
                <span className="tabular w-28 text-right">{taka(x.amount, lang)}</span>
                <span className="w-full text-xs text-muted sm:w-auto">{x.reason}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
