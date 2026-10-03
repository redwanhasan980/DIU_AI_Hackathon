import { useState } from "react";
import { api } from "../api/client";
import type { PolicyMetrics, SimulationResult } from "../api/types";
import { SegmentBars, SweepChart, TimelineChart } from "../components/charts";
import { AssumptionTag, Card, ErrorBox, Loading, Toggle } from "../components/ui";
import { ARCHETYPE_LABEL } from "../i18n/strings";
import { num, pct, shortDate, taka, takaShort } from "../lib/format";
import { useApi, useApp } from "../lib/state";

const EID_2026 = [
  { date: "2026-03-20", name: "Eid-ul-Fitr" },
  { date: "2026-05-27", name: "Eid-ul-Adha" },
];

function Compare({ label, sq, fw, fmt, lowerIsBetter = true }: {
  label: string;
  sq: number;
  fw: number;
  fmt: (v: number) => string;
  lowerIsBetter?: boolean;
}) {
  const { lang, t } = useApp();
  const change = sq ? (fw - sq) / sq : 0;
  const good = lowerIsBetter ? change <= 0 : change >= 0;
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="text-xs font-medium text-ink-2">{label}</div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <div>
          <div className="flex items-center gap-1 text-[11px] text-muted"><span className="inline-block h-2 w-2 rounded-full" style={{ background: "var(--series-2)" }} />{t.statusQuo}</div>
          <div className="tabular text-lg font-semibold">{fmt(sq)}</div>
        </div>
        <div>
          <div className="flex items-center gap-1 text-[11px] text-muted"><span className="inline-block h-2 w-2 rounded-full" style={{ background: "var(--series-1)" }} />{t.floatwise}</div>
          <div className="tabular text-lg font-semibold">{fmt(fw)}</div>
        </div>
      </div>
      <div className="mt-1 text-xs font-medium" style={{ color: good ? "var(--good-text)" : "var(--critical-text)" }}>
        {good ? "✓" : "▲"} {change > 0 ? "+" : "−"}{pct(Math.abs(change), lang, 1)}
      </div>
    </div>
  );
}

export function Impact() {
  const { lang, t } = useApp();
  const cached = useApi(() => api.simulate(), []);
  const [live, setLive] = useState<SimulationResult | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [serviceLevel, setServiceLevel] = useState(0.99);
  const [maxVisits, setMaxVisits] = useState(10);
  const [metric, setMetric] = useState<"stockouts" | "failed">("stockouts");

  if (cached.error) return <ErrorBox message={cached.error} />;
  if (!cached.data) return <Loading text={t.loading} />;
  const sim = live ?? cached.data;
  const a: PolicyMetrics = sim.status_quo;
  const b: PolicyMetrics = sim.floatwise;
  const per = sim.per_1000_agents_month;

  const rerun = async () => {
    setRunning(true);
    setRunError(null);
    try {
      setLive(await api.simulate({ service_level: serviceLevel, max_visits: maxVisits }));
    } catch (e) {
      setRunError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">{t.impactTitle}</h1>
        <p className="text-sm text-ink-2">
          {shortDate(sim.start, lang)} – {shortDate(sim.end, lang)} 2026 · {num(sim.n_agents, lang)} {lang === "bn" ? "এজেন্ট" : "agents"} ·{" "}
          {lang === "bn" ? "একই প্রকৃত চাহিদায় দুই পদ্ধতি; টেস্ট সময়কাল কখনো টিউনিংয়ে ব্যবহার হয়নি" : "same true demand for both policies; the test period was never used for tuning"}
          {" "}· {sim.source === "cache" ? (lang === "bn" ? "সংরক্ষিত ফলাফল" : "cached default run") : (lang === "bn" ? "লাইভ সিমুলেশন" : "live run")}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Compare label={t.stockoutDays} sq={a.stockout_agent_days} fw={b.stockout_agent_days} fmt={(v) => num(v, lang)} />
        <Compare label={t.failedValue} sq={a.failed_cashout_bdt + a.failed_cashin_bdt} fw={b.failed_cashout_bdt + b.failed_cashin_bdt} fmt={(v) => takaShort(v, lang)} />
        <Compare label={t.cashHeld} sq={a.avg_cash_held_bdt} fw={b.avg_cash_held_bdt} fmt={(v) => takaShort(v, lang)} />
        <Compare label={t.trips} sq={a.rebalancing_trips} fw={b.rebalancing_trips} fmt={(v) => num(v, lang)} />
        <Compare label={lang === "bn" ? "upay-এর হারানো ফি আয়" : "upay fee revenue lost"} sq={a.lost_upay_fee_bdt} fw={b.lost_upay_fee_bdt} fmt={(v) => takaShort(v, lang)} />
        <Compare label={lang === "bn" ? "এজেন্ট + ডিস্ট্রিবিউটরের হারানো কমিশন" : "Agent + distributor commission lost"} sq={a.lost_commission_bdt} fw={b.lost_commission_bdt} fmt={(v) => takaShort(v, lang)} />
        <Compare label={lang === "bn" ? "ঝুঁকিতে গ্রাহক" : "Customers at risk of leaving"} sq={a.customers_at_risk} fw={b.customers_at_risk} fmt={(v) => num(v, lang)} />
        <Compare label={lang === "bn" ? "ব্যর্থ ক্যাশ আউট" : "Failed cash-outs"} sq={a.failed_cashout_count} fw={b.failed_cashout_count} fmt={(v) => num(v, lang)} />
      </div>

      {sim.upay_network_month?.agents ? (
        <Card title={lang === "bn" ? `upay নেটওয়ার্কে (${num(sim.upay_network_month.agents, lang)} এজেন্ট) প্রতি মাসে` : `Across upay's network (${num(sim.upay_network_month.agents, lang)} agents), per month`}
          subtitle={<>{lang === "bn" ? "ব্যাকটেস্টের রৈখিক হিসাব; এজেন্ট সংখ্যা ২০২৩ সালের প্রকাশিত তথ্য" : "Linear scale-up of the backtest; agent count as published for end-2023"}<AssumptionTag /></>}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm md:grid-cols-5">
            {[
              [lang === "bn" ? "ফেরত upay ফি আয়" : "upay fee revenue protected", taka(sim.upay_network_month.upay_fee_recovered_bdt, lang)],
              [lang === "bn" ? "রক্ষা পাওয়া লেনদেন মূল্য" : "Transaction value served", takaShort(sim.upay_network_month.failed_value_avoided_bdt, lang)],
              [lang === "bn" ? "ফেরত কমিশন" : "Agent + distributor commission", taka(sim.upay_network_month.commission_recovered_bdt, lang)],
              [lang === "bn" ? "এড়ানো ঘাটতি-দিন" : "Stockout days avoided", num(sim.upay_network_month.stockout_days_avoided, lang)],
              [lang === "bn" ? "ধরে রাখা গ্রাহক" : "Customers retained", num(sim.upay_network_month.customers_retained, lang)],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-muted">{k}</dt>
                <dd className="tabular text-base font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
      ) : null}

      <Card title={lang === "bn" ? "দৈনিক তুলনা — ঈদ ২০২৬ সহ" : "Day by day — including Eid 2026"}
        right={<Toggle label="Metric" value={metric} onChange={setMetric} options={[{ value: "stockouts", label: t.stockoutDays }, { value: "failed", label: t.failedValue }]} />}>
        <TimelineChart data={sim.timeline} events={EID_2026} lang={lang} metric={metric} />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t.per1000} subtitle={<>{lang === "bn" ? "ব্যাকটেস্ট থেকে রৈখিক হিসাব" : "Linear scale-up of the backtest"}<AssumptionTag /></>}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            {[
              [lang === "bn" ? "এড়ানো ঘাটতি-দিন" : "Stockout days avoided", num(per.stockout_days_avoided, lang)],
              [lang === "bn" ? "এড়ানো ব্যর্থ লেনদেন" : "Failed transactions avoided", num(per.failed_transactions_avoided, lang)],
              [lang === "bn" ? "রক্ষা পাওয়া লেনদেন মূল্য" : "Transaction value served", taka(per.failed_value_avoided_bdt, lang)],
              [lang === "bn" ? "ফেরত কমিশন (এজেন্ট+ডিস্ট্রি.)" : "Commission recovered (agent+distributor)", taka(per.commission_recovered_bdt, lang)],
              [lang === "bn" ? "ফেরত upay ফি আয়" : "upay fee revenue protected", taka(per.upay_fee_recovered_bdt ?? 0, lang)],
              [lang === "bn" ? "ধরে রাখা গ্রাহক" : "Customers retained", num(per.customers_retained, lang)],
              [lang === "bn" ? "অতিরিক্ত ট্রিপ" : "Extra rebalancing trips", num(per.extra_trips, lang)],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-muted">{k}</dt>
                <dd className="tabular text-base font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title={lang === "bn" ? "এলাকার ধরন অনুযায়ী ঘাটতি-দিন" : "Stockout days by area type"}>
          <SegmentBars data={sim.by_archetype} lang={lang} labelOf={(s) => ARCHETYPE_LABEL[lang][s] ?? s} />
        </Card>
      </div>

      <Card title={t.tradeoff}
        subtitle={lang === "bn" ? "বেশি সেবার মাত্রা = কম ঘাটতি, কিন্তু বেশি নগদ মজুদ। পূর্বনির্ধারিত মান ভ্যালিডেশন সময়কালে বাছাই করা।" : "Higher service level = fewer stockouts but more cash held. The default was chosen on the validation period."}>
        {sim.sweep.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            <SweepChart data={sim.sweep} field="stockout_agent_days" title={t.stockoutDays} lang={lang} baseline={a.stockout_agent_days} current={sim.params.service_level} />
            <SweepChart data={sim.sweep} field="avg_cash_held_bdt" title={t.cashHeld} lang={lang} baseline={a.avg_cash_held_bdt} current={sim.params.service_level} />
          </div>
        ) : (
          <p className="text-sm text-muted">{lang === "bn" ? "এই রানে সুইপ নেই" : "No sweep in this run."}</p>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4 text-sm">
          <label className="flex items-center gap-2 text-ink-2">
            {t.serviceLevel}
            <input type="range" min={0.8} max={0.99} step={0.01} value={serviceLevel} onChange={(e) => setServiceLevel(Number(e.target.value))} />
            <span className="tabular w-10 text-ink">{pct(serviceLevel, lang)}</span>
          </label>
          <label className="flex items-center gap-2 text-ink-2">
            {t.maxVisits}<AssumptionTag />
            <input type="number" min={0} max={50} value={maxVisits} onChange={(e) => setMaxVisits(Number(e.target.value))}
              className="tabular w-16 rounded-md border border-line bg-surface px-2 py-1 text-ink" />
          </label>
          <button type="button" disabled={running} onClick={rerun} className="rounded-md bg-accent px-3 py-1.5 font-medium text-white disabled:opacity-60">
            {running ? t.loading : t.runLive}
          </button>
          {live && <button type="button" onClick={() => setLive(null)} className="text-xs text-ink-2 underline">{lang === "bn" ? "সংরক্ষিত ফলাফলে ফিরুন" : "back to cached run"}</button>}
          {runError && <span className="text-sm" style={{ color: "var(--critical-text)" }}>{runError}</span>}
        </div>
      </Card>
    </div>
  );
}
