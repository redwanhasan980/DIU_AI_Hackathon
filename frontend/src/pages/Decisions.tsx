import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ActionBadge, Card, ErrorBox, Kpi, Loading } from "../components/ui";
import { num, pct, taka, takaShort } from "../lib/format";
import { useApi, useApp } from "../lib/state";

export function Decisions() {
  const { lang, t } = useApp();
  const list = useApi(() => api.decisions(), []);
  const summary = useApi(() => api.decisionSummary(), []);
  if (list.error) return <ErrorBox message={list.error} />;
  if (!list.data) return <Loading text={t.loading} />;
  const rows = [...list.data].reverse();
  const s = summary.data;
  return (
    <div className="space-y-4">
    {s && s.total > 0 && (
      <div className="grid gap-3 lg:grid-cols-5">
        <Kpi label={lang === "bn" ? "মোট সিদ্ধান্ত" : "Decisions"} value={num(s.total, lang)} />
        <Kpi label={lang === "bn" ? "অনুমোদনের হার" : "Approval rate"} value={pct(s.approval_rate, lang)}
          sub={`${t.approve} ${num(s.by_decision.approve, lang)} · ${t.modify} ${num(s.by_decision.modify, lang)} · ${t.reject} ${num(s.by_decision.reject, lang)}`} />
        <Kpi label={lang === "bn" ? "গড় পরিবর্তন" : "Avg. modification"}
          value={s.avg_modify_change_pct === null ? "—" : `${s.avg_modify_change_pct > 0 ? "+" : ""}${pct(s.avg_modify_change_pct / 100, lang, 1)}`}
          sub={lang === "bn" ? "পরামর্শের তুলনায় চূড়ান্ত পরিমাণ" : "final vs recommended amount"} />
        <Kpi label={lang === "bn" ? "পরামর্শ বনাম চূড়ান্ত" : "Recommended → final"}
          value={`${takaShort(s.recommended_bdt, lang)} → ${takaShort(s.final_bdt, lang)}`} />
        <div className="rounded-xl border border-line bg-surface p-4">
          <div className="text-xs font-medium text-ink-2">{lang === "bn" ? "বাতিলের প্রধান কারণ" : "Top rejection reasons"}</div>
          <ul className="mt-1 space-y-0.5 text-sm">
            {s.top_rejection_reasons.length === 0 && <li className="text-muted">—</li>}
            {s.top_rejection_reasons.map((r) => (
              <li key={r.reason} className="flex justify-between gap-2"><span className="truncate">{r.reason}</span><span className="tabular text-ink-2">{num(r.count, lang)}</span></li>
            ))}
          </ul>
        </div>
      </div>
    )}
    <Card title={t.nav.decisions}
      subtitle={lang === "bn"
        ? "প্রতিটি পরামর্শ মানুষ অনুমোদন/পরিবর্তন/বাতিল করে। বাতিলের কারণ ভবিষ্যতে মডেল উন্নয়নে ব্যবহারযোগ্য।"
        : "Every recommendation is approved, modified or rejected by a person. Rejection reasons are feedback for retraining."}>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">
          {lang === "bn" ? "এখনো কোনো সিদ্ধান্ত নেই — এজেন্ট পাতায় অনুমোদন করুন।" : "No decisions yet — approve one from an agent page."}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="pb-2 font-medium">{lang === "bn" ? "সময়" : "When"}</th>
                <th className="pb-2 font-medium">{t.agent}</th>
                <th className="pb-2 font-medium">{t.action}</th>
                <th className="pb-2 font-medium">{lang === "bn" ? "সিদ্ধান্ত" : "Decision"}</th>
                <th className="pb-2 text-right font-medium">{lang === "bn" ? "পরামর্শ" : "Recommended"}</th>
                <th className="pb-2 text-right font-medium">{lang === "bn" ? "চূড়ান্ত" : "Final"}</th>
                <th className="pb-2 pl-4 font-medium">{lang === "bn" ? "কারণ" : "Reason"}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="py-1.5 text-xs text-ink-2">{d.decided_at.replace("T", " ")}</td>
                  <td className="py-1.5"><Link className="hover:underline" to={`/agents/${d.agent_id}`}>{d.agent_id}</Link></td>
                  <td className="py-1.5"><ActionBadge action={d.action} lang={lang} /></td>
                  <td className="py-1.5">{d.decision}</td>
                  <td className="tabular py-1.5 text-right">{taka(d.recommended_amount, lang)}</td>
                  <td className="tabular py-1.5 text-right">{taka(d.final_amount, lang)}</td>
                  <td className="py-1.5 pl-4 text-ink-2">{d.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
    </div>
  );
}
