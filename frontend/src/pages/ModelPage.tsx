import { api } from "../api/client";
import { AssumptionTag, Card, ErrorBox, Loading } from "../components/ui";
import { ARCHETYPE_LABEL } from "../i18n/strings";
import { num, pct, taka } from "../lib/format";
import { useApi, useApp } from "../lib/state";

const SLICES = ["overall", "event_days", "salary_window", "normal_days", "rural", "urban"];

export function ModelPage() {
  const { lang, t } = useApp();
  const report = useApi(() => api.modelReport(), []);
  if (report.error) return <ErrorBox message={report.error} />;
  if (!report.data) return <Loading text={t.loading} />;
  const { metrics, fairness, policy_tuning, assumptions } = report.data;
  const co = metrics.test.cashout;
  const label = (k: string) => {
    const name = k.replace("archetype:", "").replace("horizon:", "h=");
    return ARCHETYPE_LABEL[lang][name] ?? name.replace("_", " ");
  };

  return (
    <div className="space-y-4">
      <Card title={lang === "bn" ? "গ্রহণযোগ্যতা (SRS §6.4)" : "Acceptance checks (SRS §6.4)"}
        subtitle={`model ${metrics.version} · ${metrics.generated_at} · ${lang === "bn" ? "টেস্ট: ২০২৬ জানু–জুন, প্রকৃত চাহিদার বিপরীতে" : "test: Jan–Jun 2026, against true demand"}`}>
        <ul className="grid gap-2 sm:grid-cols-2">
          {Object.entries(metrics.acceptance.checks).map(([k, ok]) => (
            <li key={k} className="flex items-center gap-2 text-sm">
              <span aria-hidden className="flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold text-white"
                style={{ background: ok ? "var(--good)" : "var(--critical)" }}>{ok ? "✓" : "✕"}</span>
              <span className="text-ink">{k.replace(/_/g, " ")}</span>
              <span className="text-xs text-muted">{ok ? "pass" : "fail"}</span>
            </li>
          ))}
        </ul>
      </Card>

      <Card title={lang === "bn" ? "পূর্বাভাসের ত্রুটি (ক্যাশ আউট, WAPE — কম ভালো)" : "Forecast error — cash-out WAPE (lower is better)"}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="pb-2 font-medium">{lang === "bn" ? "অংশ" : "Slice"}</th>
                <th className="pb-2 text-right font-medium">FloatWise</th>
                <th className="pb-2 text-right font-medium">{lang === "bn" ? "গত সপ্তাহের একই দিন" : "Same day last week"}</th>
                <th className="pb-2 text-right font-medium">{lang === "bn" ? "৭ দিনের গড়" : "7-day average"}</th>
                <th className="pb-2 text-right font-medium">{lang === "bn" ? "উন্নতি" : "Improvement"}</th>
                <th className="pb-2 text-right font-medium">P10–P90 {lang === "bn" ? "কভারেজ" : "coverage"}</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {[...SLICES, ...Object.keys(co).filter((k) => k.startsWith("archetype:") || k.startsWith("horizon:"))].filter((k) => co[k]).map((k) => (
                <tr key={k} className="border-t border-line">
                  <td className="py-1.5">{label(k)}</td>
                  <td className="py-1.5 text-right font-medium">{pct(co[k].wape_model, lang, 1)}</td>
                  <td className="py-1.5 text-right text-ink-2">{pct(co[k].wape_seasonal_naive, lang, 1)}</td>
                  <td className="py-1.5 text-right text-ink-2">{pct(co[k].wape_trailing_mean7, lang, 1)}</td>
                  <td className="py-1.5 text-right" style={{ color: "var(--good-text)" }}>−{pct(co[k].improvement_vs_seasonal_naive_pct / 100, lang, 1)}</td>
                  <td className="py-1.5 text-right">{pct(co[k].coverage_p10_p90, lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted">
          {lang === "bn"
            ? "ঈদের দিনগুলোতে P10–P90 কভারেজ কম — মডেল চরম চাহিদায় কিছুটা অতি-আত্মবিশ্বাসী; তাই সেবার মাত্রা উঁচুতে রাখা হয়েছে।"
            : "Event-day P10–P90 coverage is below target: the model is somewhat over-confident at spikes, which is why the policy uses a high service level."}
        </p>
      </Card>

      {fairness && (
        <Card title={lang === "bn" ? "ন্যায্যতা — প্রতিটি অংশ" : "Fairness — every segment"}
          subtitle={fairness.all_segments_ok
            ? (lang === "bn" ? "কোনো অংশ বেসলাইনের চেয়ে খারাপ নয়" : "No segment is worse than the baseline")
            : `⚠ flagged: ${fairness.flagged_segments.join(", ")}`}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="pb-2 font-medium">{lang === "bn" ? "অংশ" : "Segment"}</th>
                  <th className="pb-2 text-right font-medium">{lang === "bn" ? "এজেন্ট" : "Agents"}</th>
                  <th className="pb-2 text-right font-medium">WAPE</th>
                  <th className="pb-2 text-right font-medium">{t.statusQuo}</th>
                  <th className="pb-2 text-right font-medium">FloatWise</th>
                  <th className="pb-2 text-right font-medium">{lang === "bn" ? "কম ঘাটতি" : "Fewer stockouts"}</th>
                  <th className="pb-2 text-right font-medium">OK</th>
                </tr>
              </thead>
              <tbody className="tabular">
                {fairness.segments.map((s) => (
                  <tr key={s.segment} className="border-t border-line">
                    <td className="py-1.5">{ARCHETYPE_LABEL[lang][s.segment] ?? s.segment}</td>
                    <td className="py-1.5 text-right">{num(s.n_agents, lang)}</td>
                    <td className="py-1.5 text-right">{pct(s.wape_model, lang, 1)}</td>
                    <td className="py-1.5 text-right text-ink-2">{num(s.status_quo_stockouts, lang)}</td>
                    <td className="py-1.5 text-right">{num(s.floatwise_stockouts, lang)}</td>
                    <td className="py-1.5 text-right font-medium">−{pct(s.stockout_reduction_pct / 100, lang, 1)}</td>
                    <td className="py-1.5 text-right">{s.forecast_beats_baseline && s.service_not_worse ? "✓" : "⚠"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted">
            {lang === "bn"
              ? "গ্রামীণ এজেন্টদের উন্নতি কম, কারণ ঈদের আগে তাদের মোট ফ্লোট চাহিদার তুলনায় ছোট — এজন্য ‘অতিরিক্ত ফ্লোট’ এস্কেলেশন।"
              : "Rural agents gain less: their total float is small relative to the pre-Eid spike — that is what the extra-float escalation is for."}
          </p>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {policy_tuning && (
          <Card title={lang === "bn" ? "নীতি টিউনিং (ভ্যালিডেশন)" : "Policy tuning (validation only)"} subtitle={`${policy_tuning.period} · ${policy_tuning.rule}`}>
            <p className="text-sm">
              {t.serviceLevel} <strong>{pct(policy_tuning.selected.service_level, lang)}</strong>, θ <strong>{policy_tuning.selected.risk_threshold}</strong> →{" "}
              {lang === "bn" ? "ভ্যালিডেশনে কম ঘাটতি" : "validation stockout reduction"} <strong>{pct(policy_tuning.selected.stockout_reduction_pct / 100, lang, 1)}</strong>
            </p>
          </Card>
        )}
        <Card title={<>{lang === "bn" ? "অনুমানসমূহ" : "Assumptions"}<AssumptionTag /></>}
          subtitle={lang === "bn" ? "দৃষ্টান্তমূলক — upay-এর প্রকৃত ট্যারিফ নয়" : "Illustrative — not upay tariffs"}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            {Object.entries({ ...assumptions.business, ...assumptions.dso }).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-ink-2">{k.replace(/_/g, " ")}</dt>
                <dd className="tabular text-right">{k.includes("cash") && v > 1000 ? taka(v, lang) : v < 1 ? pct(v, lang, 2) : num(v, lang)}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>
    </div>
  );
}
