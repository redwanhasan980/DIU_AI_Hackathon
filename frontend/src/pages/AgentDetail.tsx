import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Recommendation } from "../api/types";
import { DriversChart, ForecastChart } from "../components/charts";
import { ActionBadge, Card, ErrorBox, Loading, Pill, RiskBadge, Toggle, bandOf } from "../components/ui";
import { ACTION_LABEL, ARCHETYPE_LABEL, reasonLabel } from "../i18n/strings";
import { pct, shortDate, taka, weekday } from "../lib/format";
import { useApi, useApp } from "../lib/state";

function DecisionBox({ rec }: { rec: Recommendation }) {
  const { t, canDecide } = useApp();
  const [amount, setAmount] = useState(rec.amount);
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [requestKey, setRequestKey] = useState<{ payload: string; key: string } | null>(null);
  if (rec.action === "NO_ACTION") return null;
  if (!canDecide) return <p className="mt-4 border-t border-line pt-4 text-sm text-ink-2">{t.readOnlyNotice}</p>;

  const send = async (decision: "approve" | "modify" | "reject") => {
    if (sending) return;
    setError(null);
    setSending(true);
    const body = {
      agent_id: rec.agent_id, date: rec.date, action: rec.action, recommended_amount: rec.amount,
      balance_version: rec.balance_version,
      history_revision: rec.history_revision, model_version: rec.model_version, policy_version: rec.policy_version,
      final_amount: decision === "reject" ? 0 : decision === "modify" ? amount : rec.amount, decision, reason,
    };
    const payload = JSON.stringify(body);
    const key = requestKey?.payload === payload ? requestKey.key : crypto.randomUUID();
    setRequestKey({ payload, key });
    try {
      await api.decide(body, key);
      setStatus(`${decision === "approve" ? "✓" : decision === "modify" ? "✎" : "✕"} ${t.decisionSaved}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };
  const btn = "rounded-md px-3 py-1.5 text-sm font-medium";
  return (
    <div className="mt-4 border-t border-line pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" disabled={sending} onClick={() => send("approve")} className={`${btn} bg-accent text-white hover:opacity-90`}>{t.approve}</button>
        <label className="flex items-center gap-1 text-sm text-ink-2">
          ৳
          <input type="number" min={0} step={1000} value={amount} onChange={(e) => setAmount(Number(e.target.value))}
            aria-label={t.amount} className="tabular w-28 rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink" />
        </label>
        <button type="button" disabled={sending} onClick={() => send("modify")} className={`${btn} border border-line text-ink hover:bg-surface-2`}>{t.modify}</button>
        <button type="button" disabled={sending} onClick={() => send("reject")} className={`${btn} border border-line text-ink-2 hover:bg-surface-2`}>{t.reject}</button>
        <input value={reason} onChange={(e) => setReason(e.target.value.slice(0, 300))} placeholder={t.reasonPlaceholder}
          className="min-w-40 flex-1 rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink" />
      </div>
      {status && <p role="status" className="mt-2 text-sm" style={{ color: "var(--good-text)" }}>{status}</p>}
      {error && <p role="alert" className="mt-2 text-sm" style={{ color: "var(--critical-text)" }}>{error}</p>}
    </div>
  );
}

export function AgentDetail() {
  const { id = "" } = useParams();
  const { date, lang, t } = useApp();
  const [side, setSide] = useState<"cashout" | "cashin">("cashout");
  const detail = useApi(() => api.agent(id, date), [id, date]);
  const forecast = useApi(() => api.forecast(id, date), [id, date]);
  const rec = useApi(() => api.recommendation(id, date), [id, date]);
  const expl = useApi(() => api.explanation(id, date, lang), [id, date, lang]);

  const err = detail.error ?? forecast.error ?? rec.error;
  if (err) return <ErrorBox message={err} />;
  if (!detail.data || !forecast.data || !rec.data) return <Loading text={t.loading} />;
  const a = detail.data.agent;
  const r = rec.data;
  const efloatSide = r.action === "TOP_UP_EFLOAT";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link to="/risk" className="text-xs text-muted hover:underline">← {t.nav.risk}</Link>
          <h1 className="text-xl font-semibold text-ink">{a.shop_name} <span className="text-sm font-normal text-muted">{a.agent_id}</span></h1>
          <p className="text-sm text-ink-2">
            {a.upazila}, {a.district} · {ARCHETYPE_LABEL[lang][a.archetype]} · DSO <Link className="underline" to={`/dso?dso=${a.dso_id}`}>{a.dso_id}</Link>
            {" "}· {lang === "bn" ? "মোট ফ্লোট" : "Total float"} {taka(a.float_capacity, lang)}
          </p>
        </div>
        <Link to={`/card/${a.agent_id}`} className="rounded-md border border-line px-3 py-1.5 text-sm text-ink hover:bg-surface-2">📱 {t.openAgentCard}</Link>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3" title={`${t.recommendation} ${shortDate(r.effective_date, lang)}`}
          subtitle={`${t.serviceLevel} ${pct(r.service_level, lang)} · ${lang === "bn" ? "সিদ্ধান্ত ইঞ্জিন" : "decision engine"}`}
          right={<RiskBadge band={a.risk_band} p={Math.max(r.p_cash_stockout, r.p_efloat_stockout)} lang={lang} />}>
          <div className="flex flex-wrap items-baseline gap-3">
            <ActionBadge action={r.action} lang={lang} />
            {r.amount > 0 && <span className="text-3xl font-semibold text-ink">{taka(r.amount, lang)}</span>}
          </div>
          <p className="mt-2 text-sm text-ink-2">
            {r.action === "TOP_UP_CASH" && (lang === "bn" ? "ডিএসও নগদ টাকা পৌঁছে দেবে; এজেন্ট সমপরিমাণ ই-ফ্লোট পাঠাবে।" : "DSO delivers cash; the agent sends the same amount of e-float back.")}
            {r.action === "TOP_UP_EFLOAT" && (lang === "bn" ? "ডিএসও নগদ নেবে এবং সমপরিমাণ ই-ফ্লোট পাঠাবে।" : "DSO collects cash and sends the same amount of e-float.")}
            {r.action === "NEEDS_EXTRA_FLOAT" && (lang === "bn" ? `মোট ফ্লোটে ${taka(r.extra_float_needed, lang)} ঘাটতি — ডিস্ট্রিবিউটর সিদ্ধান্ত নেবেন।` : `Total float is ${taka(r.extra_float_needed, lang)} short even at P90 — distributor decides on extra float.`)}
            {r.action === "NO_ACTION" && (lang === "bn" ? "বর্তমান ব্যালেন্স যথেষ্ট।" : "Current balances are enough.")}
          </p>

          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            {([["cash", r.open_cash, r.cash_target, r.p_cash_stockout], ["efloat", r.open_efloat, r.efloat_target, r.p_efloat_stockout]] as const).map(
              ([k, have, need, p]) => (
                <div key={k} className={`rounded-lg border p-3 ${(k === "efloat") === efloatSide ? "border-[var(--accent)]" : "border-line"}`}>
                  <div className="text-xs text-muted">{k === "cash" ? t.cash : t.efloat}</div>
                  <div className="tabular mt-1 flex justify-between"><span className="text-ink-2">{t.balances}</span><span className="font-medium">{taka(have, lang)}</span></div>
                  <div className="tabular flex justify-between"><span className="text-ink-2">{t.need}</span><span className="font-medium">{taka(need, lang)}</span></div>
                  <div className="mt-1"><RiskBadge band={bandOf(p)} p={p} lang={lang} /></div>
                </div>
              ),
            )}
          </div>

          <div className="mt-4">
            <div className="mb-1 text-xs font-medium text-muted">{t.reasons}</div>
            <div className="flex flex-wrap gap-1.5">
              {r.reason_codes.map((c) => <Pill key={c} tone={c.startsWith("EID") ? "warn" : "neutral"}>{reasonLabel(c, lang)}</Pill>)}
            </div>
          </div>

          <div className="mt-4">
            <div className="mb-1 text-xs font-medium text-muted">{t.outlook}</div>
            <div className="grid grid-cols-7 gap-1">
              {r.outlook.map((o) => {
                const p = Math.max(o.p_cash_stockout, o.p_efloat_stockout);
                const band = bandOf(p);
                return (
                  <div key={o.date} title={`${shortDate(o.date, lang)} ${pct(p, lang)}`}
                    className="rounded-md border border-line p-1.5 text-center"
                    style={{ borderTop: `3px solid ${band === "high" ? "var(--critical)" : band === "medium" ? "var(--warning)" : "var(--good)"}` }}>
                    <div className="text-[10px] text-muted">{weekday(o.date, lang)}</div>
                    <div className="text-[11px] text-ink-2">{shortDate(o.date, lang)}</div>
                    <div className="tabular text-xs font-semibold">{pct(p, lang)}</div>
                  </div>
                );
              })}
            </div>
          </div>
          <DecisionBox key={`${r.agent_id}-${r.date}`} rec={r} />
        </Card>

        <Card className="lg:col-span-2"
          title={expl.data?.source === "llm" ? t.aiExplanation : expl.data?.source === "cache" ? t.cachedExplanation : t.templateExplanation}
          subtitle={t.explanationNote}>
          {expl.error && <ErrorBox message={expl.error} />}
          {!expl.data && !expl.error && <Loading text={t.loading} />}
          {expl.data && (
            <blockquote className="rounded-lg border-l-4 border-[var(--accent)] bg-surface-2 p-3 text-[15px] leading-relaxed text-ink">
              {expl.data.narrative}
            </blockquote>
          )}
          <p className="mt-2 text-xs text-muted">
            {ACTION_LABEL[lang][r.action]} · {lang === "bn" ? "উৎস" : "source"}: {expl.data?.source ?? "…"}
          </p>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3" title={t.forecastTitle}
          subtitle={lang === "bn" ? "বাম দিকে প্রকৃত (পরিবেশিত) লেনদেন; ড্যাশ লাইন থেকে পূর্বাভাস" : "Left of the dashed line: observed (served) volume. Right: forecast range and the synthetic true demand."}
          right={<Toggle label="Side" value={side} onChange={setSide} options={[{ value: "cashout", label: t.cashout }, { value: "cashin", label: t.cashin }]} />}>
          <ForecastChart history={detail.data.history} forecast={forecast.data} side={side} lang={lang} />
        </Card>
        <Card className="lg:col-span-2" title={t.drivers} subtitle={t.driversNote}>
          {expl.data ? <DriversChart drivers={expl.data.drivers} lang={lang} /> : <Loading text={t.loading} />}
          {expl.data && (
            <p className="tabular mt-2 text-xs text-muted">
              {lang === "bn" ? "ভিত্তি" : "Baseline"} {taka(expl.data.base_bdt, lang)} → {lang === "bn" ? "মিডিয়ান মডেলের আউটপুট" : "median-model output"} {taka(expl.data.forecast_p50_bdt, lang)}
            </p>
          )}
          {expl.data && (() => {
            const p = forecast.data.points[0][r.action === "TOP_UP_EFLOAT" ? "cashin" : "cashout"].p50;
            return Math.abs(p - expl.data.forecast_p50_bdt) > 0.01 * Math.max(p, 1) ? (
              <p className="mt-1 text-xs text-muted">
                {lang === "bn"
                  ? `দেখানো P50 (${taka(p, lang)}) ভিন্ন, কারণ P10 ≤ P50 ≤ P90 নিশ্চিত করতে কোয়ান্টাইলগুলো পুনর্বিন্যাস করা হয়েছে।`
                  : `Displayed P50 (${taka(p, lang)}) differs: quantiles are re-ordered to keep P10 ≤ P50 ≤ P90 (rearrangement).`}
              </p>
            ) : null;
          })()}
        </Card>
      </div>
    </div>
  );
}
