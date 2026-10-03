import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ActionBadge, Card, ErrorBox, Loading } from "../components/ui";
import { taka } from "../lib/format";
import { useApi, useApp } from "../lib/state";

export function Decisions() {
  const { lang, t } = useApp();
  const list = useApi(() => api.decisions(), []);
  if (list.error) return <ErrorBox message={list.error} />;
  if (!list.data) return <Loading text={t.loading} />;
  const rows = [...list.data].reverse();
  return (
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
                <th className="pb-2 font-medium">{lang === "bn" ? "কারণ" : "Reason"}</th>
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
                  <td className="py-1.5 text-ink-2">{d.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
