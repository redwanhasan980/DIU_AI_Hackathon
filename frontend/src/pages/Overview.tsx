import { Link } from "react-router-dom";
import { api } from "../api/client";
import { MapLegend, NetworkMap } from "../components/NetworkMap";
import { Card, ErrorBox, Kpi, Loading } from "../components/ui";
import { eventName } from "../i18n/strings";
import { num, pct, shortDate, taka, takaShort } from "../lib/format";
import { useApi, useApp } from "../lib/state";

export function EventBanner({ events }: { events: { name: string; date: string; days_to: number }[] }) {
  const { lang, t } = useApp();
  const next = events.find((e) => e.name.startsWith("Eid")) ?? events[0];
  if (!next) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--warning)] bg-surface px-4 py-3 text-sm">
      <span aria-hidden className="text-lg">☪</span>
      <strong className="text-ink">{t.eventIn(eventName(next.name, lang), next.days_to)}</strong>
      <span className="text-ink-2">({shortDate(next.date, lang)})</span>
      <span className="text-muted">
        · {events.filter((e) => e !== next).map((e) => `${eventName(e.name, lang)} ${shortDate(e.date, lang)}`).join(" · ")}
      </span>
    </div>
  );
}

export function Overview() {
  const { date, lang, t } = useApp();
  const summary = useApi(() => api.network(date), [date]);
  const agents = useApi(() => api.agents(date), [date]);
  const sim = useApi(() => api.cachedSimulation(), []);

  if (summary.error) return <ErrorBox message={summary.error} />;
  if (!summary.data) return <Loading text={t.loading} />;
  const s = summary.data;
  const acting = s.n_agents - (s.by_action.NO_ACTION ?? 0);

  return (
    <div className="space-y-4">
      <EventBanner events={s.upcoming_events} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label={t.agentsAtRisk} value={`${num(acting, lang)} / ${num(s.n_agents, lang)}`} sub={`${t.highRisk}: ${num(s.by_band.high, lang)}`} />
        <Kpi label={t.cashToDeliver} value={takaShort(s.recommended_cash, lang)} sub={taka(s.recommended_cash, lang)} />
        <Kpi label={t.efloatToSend} value={takaShort(s.recommended_efloat, lang)} sub={taka(s.recommended_efloat, lang)} />
        <Kpi label={t.escalations} value={num(s.by_action.NEEDS_EXTRA_FLOAT ?? 0, lang)} sub={lang === "bn" ? "মানুষের সিদ্ধান্ত দরকার" : "need a human decision"} />
        {sim.data ? (
          <Link to="/impact" className="block">
            <Kpi
              label={lang === "bn" ? "ব্যাকটেস্ট: কম ঘাটতি" : "Backtest: fewer stockouts"}
              value={`−${pct(sim.data.improvement_pct.stockout_agent_days / 100, lang, 1)}`}
              sub={lang === "bn" ? "২০২৬ জানু–জুন, ঈদসহ →" : "Jan–Jun 2026 incl. Eid →"}
              tone="good"
            />
          </Link>
        ) : (
          <Kpi label="Backtest" value="…" />
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" title={lang === "bn" ? "এজেন্ট ঝুঁকির মানচিত্র" : "Agent risk map"}
          subtitle={lang === "bn" ? `${shortDate(date, lang)} রাতের ব্যালেন্সে আগামীকালের ঘাটতির ঝুঁকি` : `Risk of a stockout tomorrow from balances at close of ${shortDate(date, lang)}`}>
          {agents.data ? <NetworkMap agents={agents.data} lang={lang} /> : <Loading text={t.loading} />}
          <MapLegend lang={lang} />
        </Card>
        <Card title={t.districts}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="pb-2 font-medium">{lang === "bn" ? "জেলা" : "District"}</th>
                <th className="pb-2 text-right font-medium">{t.highRisk}</th>
                <th className="pb-2 text-right font-medium">{t.cashToDeliver}</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {s.by_district.slice(0, 12).map((d) => (
                <tr key={d.district} className="border-t border-line">
                  <td className="py-1.5">
                    <Link className="hover:underline" to={`/risk?district=${encodeURIComponent(d.district)}`}>{d.district}</Link>
                  </td>
                  <td className="py-1.5 text-right">{num(d.n_high, lang)}/{num(d.n_agents, lang)}</td>
                  <td className="py-1.5 text-right">{takaShort(d.recommended_cash, lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
