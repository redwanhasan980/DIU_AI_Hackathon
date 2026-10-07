import { useState } from "react";
import { api } from "../api/client";
import type { BalanceState, LiveForecast } from "../api/types";
import { ForecastChart } from "../components/charts";
import { Card } from "../components/ui";
import { useApp } from "../lib/state";

export function Operations() {
  const { date, lang, t } = useApp();
  const [id, setId] = useState("AG00471");
  const [loaded, setLoaded] = useState<{ id: string; date: string; balance: BalanceState } | null>(null);
  const [cash, setCash] = useState(0);
  const [forecast, setForecast] = useState<LiveForecast | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const balance = loaded?.id === id && loaded.date === date ? loaded.balance : null;
  const btn = "rounded-md bg-accent px-3 py-2 text-sm text-white disabled:opacity-50";
  const perform = async (action: () => Promise<void>) => {
    setBusy(true); setError(null); setMessage(null);
    try { await action(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return <div className="space-y-4">
    <h1 className="text-xl font-semibold">{t.operationsTitle}</h1>
    <Card title={t.balances} subtitle={t.operationsNote}>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">{t.agent}<input className="mt-1 block rounded border border-line bg-surface px-2 py-1" value={id} onChange={(e) => { setId(e.target.value); setForecast(null); }} /></label>
        <button type="button" className={btn} disabled={busy} onClick={() => perform(async () => {
          const b = await api.balance(id, date); setLoaded({ id, date, balance: b }); setCash(b.cash);
        })}>{t.loadBalances}</button>
        <button type="button" className={btn} disabled={busy} onClick={() => perform(async () => {
          setForecast(await api.liveForecast(id, date));
        })}>{t.runForecast}</button>
      </div>
      {balance && <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="text-sm">{t.cash}<input type="number" min={0} max={balance.cash + balance.efloat} step={1} value={cash}
          onChange={(e) => setCash(Number(e.target.value))} className="mt-1 block rounded border border-line bg-surface px-2 py-1" /></label>
        <p className="text-sm">{t.efloat}: {balance.cash + balance.efloat - cash} · {t.balanceVersion}: {balance.version}</p>
        <button type="button" className={btn} disabled={busy || !Number.isInteger(cash) || cash < 0 || cash > balance.cash + balance.efloat}
          onClick={() => perform(async () => {
            const b = await api.observeBalance(id, date, cash, balance.cash + balance.efloat - cash, balance.version);
            setLoaded({ id, date, balance: b }); setMessage(t.observationSaved);
            window.dispatchEvent(new Event("fw-balances"));
          })}>{t.saveBalances}</button>
      </div>}
      {message && <p role="status" className="mt-3 text-sm">{message}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-[var(--critical-text)]">{error}</p>}
    </Card>
    {forecast?.agent_id === id && forecast.origin === date && <Card title={t.forecastTitle} subtitle={`${forecast.source} · ${forecast.model_version}`}>
      <ForecastChart history={[]} forecast={forecast} side="cashout" lang={lang} />
    </Card>}
  </div>;
}
