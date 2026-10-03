import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { Action, AgentSummary } from "../api/types";
import { ActionBadge, Card, ErrorBox, Loading, RiskBadge } from "../components/ui";
import { ACTION_LABEL, ARCHETYPE_LABEL } from "../i18n/strings";
import { num, taka } from "../lib/format";
import { useApi, useApp } from "../lib/state";

type SortKey = "p_stockout" | "amount" | "shop_name";

export function RiskList() {
  const { date, lang, t } = useApp();
  const [params, setParams] = useSearchParams();
  const district = params.get("district") ?? "";
  const archetype = params.get("archetype") ?? "";
  const action = (params.get("action") ?? "") as Action | "";
  const [sort, setSort] = useState<SortKey>("p_stockout");
  const agents = useApi(() => api.agents(date), [date]);

  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };

  const rows = useMemo(() => {
    const list = (agents.data ?? []).filter(
      (a) => (!district || a.district === district) && (!archetype || a.archetype === archetype) && (!action || a.action === action),
    );
    const cmp: Record<SortKey, (a: AgentSummary, b: AgentSummary) => number> = {
      p_stockout: (a, b) => b.p_stockout - a.p_stockout,
      amount: (a, b) => b.amount - a.amount,
      shop_name: (a, b) => a.shop_name.localeCompare(b.shop_name),
    };
    return [...list].sort(cmp[sort]);
  }, [agents.data, district, archetype, action, sort]);

  if (agents.error) return <ErrorBox message={agents.error} />;
  if (!agents.data) return <Loading text={t.loading} />;
  const districts = [...new Set(agents.data.map((a) => a.district))].sort();
  const select = "rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink";
  const th = (key: SortKey, label: string, right = false) => (
    <th className={`pb-2 font-medium ${right ? "text-right" : ""}`}>
      <button type="button" onClick={() => setSort(key)} className={sort === key ? "text-ink underline" : "hover:text-ink"}>
        {label}
      </button>
    </th>
  );

  return (
    <Card
      title={`${t.nav.risk} · ${num(rows.length, lang)}`}
      right={
        <div className="flex flex-wrap gap-2">
          <select aria-label="District" className={select} value={district} onChange={(e) => set("district", e.target.value)}>
            <option value="">{lang === "bn" ? "সব জেলা" : "All districts"}</option>
            {districts.map((d) => <option key={d}>{d}</option>)}
          </select>
          <select aria-label="Area type" className={select} value={archetype} onChange={(e) => set("archetype", e.target.value)}>
            <option value="">{lang === "bn" ? "সব এলাকা" : "All area types"}</option>
            {Object.keys(ARCHETYPE_LABEL.en).filter((k) => k.includes("_")).map((k) => (
              <option key={k} value={k}>{ARCHETYPE_LABEL[lang][k]}</option>
            ))}
          </select>
          <select aria-label="Action" className={select} value={action} onChange={(e) => set("action", e.target.value)}>
            <option value="">{lang === "bn" ? "সব পদক্ষেপ" : "All actions"}</option>
            {(Object.keys(ACTION_LABEL.en) as Action[]).map((k) => <option key={k} value={k}>{ACTION_LABEL[lang][k]}</option>)}
          </select>
        </div>
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="text-left text-xs text-muted">
              {th("shop_name", t.agent)}
              <th className="pb-2 font-medium">{t.area}</th>
              <th className="pb-2 font-medium">{t.areaType}</th>
              {th("p_stockout", t.risk)}
              <th className="pb-2 font-medium">{t.action}</th>
              {th("amount", t.amount, true)}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 300).map((a) => (
              <tr key={a.agent_id} className="border-t border-line hover:bg-surface-2">
                <td className="py-2">
                  <Link to={`/agents/${a.agent_id}`} className="font-medium text-ink hover:underline">{a.shop_name}</Link>
                  <div className="text-xs text-muted">{a.agent_id} · {a.dso_id}</div>
                </td>
                <td className="py-2 text-ink-2">{a.upazila}, {a.district}</td>
                <td className="py-2 text-ink-2">{ARCHETYPE_LABEL[lang][a.archetype]}</td>
                <td className="py-2"><RiskBadge band={a.risk_band} p={a.p_stockout} lang={lang} /></td>
                <td className="py-2"><ActionBadge action={a.action} lang={lang} /></td>
                <td className="tabular py-2 text-right">{a.amount ? taka(a.amount, lang) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
