// Agent mobile card: Bangla-first, big text, one action (FR-UI screen 7) for low-literacy users.
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ErrorBox, Loading } from "../components/ui";
import { eventName, reasonLabel } from "../i18n/strings";
import { shortDate, taka } from "../lib/format";
import { useApi, useApp } from "../lib/state";

export function AgentCard() {
  const { id = "" } = useParams();
  const { date, lang } = useApp();
  const rec = useApi(() => api.recommendation(id, date), [id, date]);
  const detail = useApi(() => api.agent(id, date), [id, date]);
  const net = useApi(() => api.network(date), [date]);
  if (rec.error) return <ErrorBox message={rec.error} />;
  if (!rec.data || !detail.data) return <Loading />;
  const r = rec.data;
  const L = lang;
  const event = net.data?.upcoming_events.find((e) => e.name.startsWith("Eid"));
  const headline: Record<string, { icon: string; bn: string; en: string }> = {
    TOP_UP_CASH: { icon: "💵", bn: `আগামীকাল দোকান খোলার আগে ${taka(r.amount, "bn")} নগদ এনে রাখুন`, en: `Bring ${taka(r.amount)} cash before opening tomorrow` },
    TOP_UP_EFLOAT: { icon: "📲", bn: `${taka(r.amount, "bn")} নগদ ই-ফ্লোটে রূপান্তর করুন`, en: `Convert ${taka(r.amount)} cash into e-float` },
    NEEDS_EXTRA_FLOAT: { icon: "⚠️", bn: "আপনার ফ্লোট যথেষ্ট নয় — ডিএসও আপনাকে ফোন করবেন", en: "Your float is not enough — your DSO will call you" },
    NO_ACTION: { icon: "✅", bn: "আগামীকালের জন্য ব্যালেন্স ঠিক আছে", en: "Your balance is fine for tomorrow" },
  };
  const h = headline[r.action];
  return (
    <div className="mx-auto max-w-sm py-4">
      <Link to={`/agents/${id}`} className="text-xs text-muted hover:underline">← {id}</Link>
      <div className="mt-2 overflow-hidden rounded-3xl border border-line bg-surface shadow-xl">
        <div className="bg-accent px-5 py-4 text-white">
          <div className="text-xs opacity-90">upay এজেন্ট · {detail.data.agent.shop_name}</div>
          <div className="mt-1 text-lg font-semibold">{L === "bn" ? `আগামীকাল (${shortDate(r.effective_date, "bn")})` : `Tomorrow (${shortDate(r.effective_date)})`}</div>
        </div>
        <div className="space-y-4 p-5">
          <div className="flex items-start gap-3">
            <span aria-hidden className="text-4xl">{h.icon}</span>
            <p className="text-2xl font-semibold leading-snug text-ink">{L === "bn" ? h.bn : h.en}</p>
          </div>
          {event && event.days_to <= 10 && (
            <p className="rounded-xl bg-surface-2 p-3 text-base text-ink">
              🌙 {L === "bn" ? `${eventName(event.name, "bn")} আর ${String(event.days_to).replace(/\d/g, (d) => "০১২৩৪৫৬৭৮৯"[+d])} দিন বাকি — ক্যাশ আউট বাড়বে` : `${event.name} in ${event.days_to} days — cash-outs will rise`}
            </p>
          )}
          <div className="grid grid-cols-2 gap-2 text-center">
            <div className="rounded-xl border border-line p-3">
              <div className="text-sm text-muted">{L === "bn" ? "এখন নগদ" : "Cash now"}</div>
              <div className="tabular text-xl font-semibold">{taka(r.open_cash, L)}</div>
            </div>
            <div className="rounded-xl border border-line p-3">
              <div className="text-sm text-muted">{L === "bn" ? "দরকার" : "Needed"}</div>
              <div className="tabular text-xl font-semibold">{taka(r.cash_target, L)}</div>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {r.reason_codes.slice(0, 3).map((c) => (
              <span key={c} className="rounded-full bg-surface-2 px-3 py-1 text-sm text-ink-2">{reasonLabel(c, L)}</span>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button type="button" className="rounded-xl bg-accent py-3 text-lg font-semibold text-white">{L === "bn" ? "ঠিক আছে" : "OK"}</button>
            <button type="button" className="rounded-xl border border-line py-3 text-lg font-semibold text-ink">{L === "bn" ? "ডিএসও-কে ফোন" : "Call DSO"}</button>
          </div>
          <p className="text-center text-xs text-muted">{L === "bn" ? "নমুনা স্ক্রিন — কৃত্রিম ডেটা" : "Prototype screen — synthetic data"}</p>
        </div>
      </div>
    </div>
  );
}
