import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { DsoTask, Forecast, IntegrationEvent, IntegrationStatus, Recommendation } from "../api/types";
import { ForecastChart } from "../components/charts";
import { ActionBadge, Card, Kpi } from "../components/ui";
import { INTEGRATION_STRINGS } from "../i18n/integration";
import { taka } from "../lib/format";
import { useApp } from "../lib/state";

export function IntegrationPage() {
  const { date, lang, canOperate, canDecide, authStatus } = useApp();
  const t = INTEGRATION_STRINGS[lang];
  const [agent, setAgent] = useState("AG00471");
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [result, setResult] = useState<{ key: string; rec: Recommendation; forecast: Forecast } | null>(null);
  const [amount, setAmount] = useState(0);
  const [reason, setReason] = useState("");
  const [payload, setPayload] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [decisionId, setDecisionId] = useState<number | null>(null);
  const [decisionRequest, setDecisionRequest] = useState<{ payload: string; key: string } | null>(null);
  const inflight = useRef(false);
  const selectionKey = `${agent}:${date}`;
  const selection = useRef(selectionKey);
  useEffect(() => { selection.current = selectionKey; }, [selectionKey]);
  const isLive = authStatus === "signed_in";
  const input = "rounded-md border border-line bg-surface px-2 py-1 text-sm";
  const button = "rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-50 hover:bg-surface-2";
  const recommendation = result?.key === selectionKey ? result.rec : null;
  const refresh = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = true;
    try { setStatus(await api.integrationStatus()); setPollError(null); }
    catch (e) { setPollError((e as Error).message); }
    finally { inflight.current = false; }
  }, []);
  useEffect(() => {
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, 2500);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [refresh]);
  const perform = async (action: () => Promise<void>) => {
    if (busy) return;
    setBusy(true); setError(null); setNotice(null);
    try { await action(); await refresh(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const loadRecommendation = async () => {
    const key = `${agent}:${date}`;
    const [rec, forecast] = await Promise.all([api.recommendation(agent, date), api.forecast(agent, date)]);
    if (selection.current !== key) return;
    setResult({ key, rec, forecast }); setAmount(rec.amount); setDecisionId(null);
  };
  const createFromDecision = async (id: number) => { await api.createTask(id); setDecisionId(null); };
  const decide = async (decision: "approve" | "modify" | "reject") => {
    if (!recommendation) return;
    const body = { agent_id: agent, date, action: recommendation.action,
      recommended_amount: recommendation.amount, final_amount: decision === "reject" ? 0 : decision === "modify" ? amount : recommendation.amount,
      decision, reason, balance_version: recommendation.balance_version, history_revision: recommendation.history_revision,
      model_version: recommendation.model_version, policy_version: recommendation.policy_version };
    const requestPayload = JSON.stringify(body);
    const key = decisionRequest?.payload === requestPayload ? decisionRequest.key : crypto.randomUUID();
    setDecisionRequest({ payload: requestPayload, key });
    const saved = await api.decide(body, key);
    setNotice(t.saved);
    if (decision !== "reject" && saved.decision_id) {
      setDecisionId(saved.decision_id);
      await createFromDecision(saved.decision_id);
    }
  };
  const transition = async (task: DsoTask, next: "dispatched" | "accepted" | "rejected" | "cancelled") => {
    await api.taskStatus(task, next);
  };
  return <div className="space-y-4">
    <h1 className="text-xl font-semibold">{t.title}</h1>
    <p className="text-sm text-ink-2">{t.note}</p>
    <p className="rounded-lg border border-line bg-surface p-3 text-sm">{t.flow}</p>
    {!canDecide && <p className="text-sm text-ink-2">{t.readOnly}</p>}
    {!isLive && <p role="status" className="text-sm">{t.apiOnly}</p>}
    {(error || pollError) && <p role="alert" className="rounded border border-line p-3 text-sm">{error ?? pollError}</p>}
    {notice && <p role="status" className="text-sm">{notice}</p>}
    <Card title={t.connector}>
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm">{t.agent} <input value={agent} disabled={busy} onChange={e => setAgent(e.target.value)} className={input} /></label>
        <span className="text-sm">{date}</span>
        {canOperate && <>
          <button type="button" className={button} disabled={busy || !isLive || !status?.worker.online || ["running", "paused"].includes(status.connector.status)} onClick={() => perform(async () => { await api.connector(agent, date, "start"); setResult(null); })}>{t.start}</button>
          <button type="button" className={button} disabled={busy || !isLive || status?.connector.status !== "running"} onClick={() => perform(async () => { await api.connector(agent, date, "pause"); })}>{t.pause}</button>
          <button type="button" className={button} disabled={busy || !isLive || !status?.worker.online || status.connector.status !== "paused"} onClick={() => perform(async () => { await api.connector(agent, date, "resume"); })}>{t.resume}</button>
          <button type="button" className={button} disabled={busy || !isLive || !status?.worker.online || !["completed", "paused", "failed"].includes(status.connector.status)} onClick={() => perform(async () => { await api.connector(agent, date, "replay"); setResult(null); })}>{t.replay}</button>
        </>}
      </div>
      {status && <div className="mt-3 space-y-1 text-sm text-ink-2">
        <p>{t.status}: {t[status.connector.status]} · {status.connector.cursor}/{status.connector.total}
          {status.connector.agent_id && ` · ${status.connector.agent_id} · ${status.connector.date}`}</p>
        <p>{t.worker}: {status.worker.online ? t.online : t.offline} · {status.worker.heartbeat_at ?? "—"}</p>
        {!status.worker.online && <p>{t.workerHint}</p>}
        <p>{status.worker.connector_configured ? t.configured : t.notConfigured}</p>
        {status.connector.error && <p role="alert">{status.connector.error}</p>}
      </div>}
    </Card>
    {status && <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Kpi label={t.queue} value={String(status.metrics.queue_depth)} />
      <Kpi label={t.received} value={String(status.metrics.processed)} />
      <Kpi label={t.failures} value={String(status.metrics.failed)} />
      <Kpi label={t.latency} value={String(status.metrics.inference_p95_ms)} />
      <Kpi label={t.lag} value={String(status.metrics.oldest_pending_seconds)} />
      <Kpi label={t.inferenceErrors} value={String(status.metrics.inference_errors)} />
      <Kpi label={t.reconcileErrors} value={String(status.metrics.reconciliation_failures)} />
      <Kpi label={t.stale} value={String(status.metrics.stale_forecasts)} />
    </div>}
    <Card title={t.forecast}>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className={button} disabled={busy || !isLive} onClick={() => perform(loadRecommendation)}>{t.refresh}</button>
        <Link className="text-sm text-accent" to={`/agents/${agent}?date=${date}`}>{t.openAgent}</Link>
      </div>
      {!recommendation && <p className="mt-3 text-sm text-ink-2">{t.waiting}</p>}
      {recommendation && <div className="mt-3 space-y-3">
        <div className="flex items-center gap-3"><ActionBadge action={recommendation.action} lang={lang} /><strong>{taka(recommendation.amount, lang)}</strong></div>
        <p className="text-xs text-muted">{t.revision}: {recommendation.history_revision} · {t.balance}: {recommendation.balance_version} · {recommendation.model_version} · {t.policy}: {recommendation.policy_version}</p>
        <p className="text-xs text-muted">{result!.forecast.source} · {result!.forecast.origin}</p>
        <ForecastChart history={[]} forecast={result!.forecast} side="cashout" lang={lang} />
        {canDecide && recommendation.action !== "NO_ACTION" && <div className="flex flex-wrap items-center gap-2">
          <button type="button" disabled={busy || !isLive || recommendation.action === "NEEDS_EXTRA_FLOAT"} className={button} onClick={() => perform(() => decide("approve"))}>{t.approve}</button>
          <label className="text-sm">{t.amount} <input type="number" min={0} step={1000} className={`${input} w-28`} value={amount} onChange={e => setAmount(Number(e.target.value))} /></label>
          <input className={input} maxLength={300} aria-label={t.reason} placeholder={t.reason} value={reason} onChange={e => setReason(e.target.value)} />
          <button type="button" disabled={busy || !isLive || amount <= 0 || !Number.isInteger(amount) || !reason.trim() || recommendation.action === "NEEDS_EXTRA_FLOAT"} className={button} onClick={() => perform(() => decide("modify"))}>{t.modify}</button>
          <button type="button" disabled={busy || !isLive} className={button} onClick={() => perform(() => decide("reject"))}>{t.reject}</button>
        </div>}
        {decisionId && <button type="button" disabled={busy || !isLive} className={button} onClick={() => perform(() => createFromDecision(decisionId))}>{t.retry} · #{decisionId}</button>}
      </div>}
    </Card>
    <Card title={t.tasks}>
      <ul className="divide-y divide-line">
        {status?.tasks.map(task => <li key={task.id} className="space-y-2 py-3">
          <div className="flex flex-wrap gap-3 text-sm"><strong>#{task.id} · {task.dso_id} · {task.agent_id}</strong><span>{t[task.status]}</span><span>{taka(task.amount, lang)}</span><span>{task.date}</span></div>
          <p className="text-xs text-muted">{t.revision}: {task.history_revision} · {t.balance}: {task.balance_revision} · {task.model_version}{task.delivery_reference && ` · ${task.delivery_reference}`}</p>
          {canDecide && <div className="flex flex-wrap gap-2">
            {task.status === "approved" && <button type="button" disabled={busy || !isLive} className={button} onClick={() => perform(() => transition(task, "dispatched"))}>{t.dispatch}</button>}
            {task.status === "dispatched" && <>
              <button type="button" disabled={busy || !isLive} className={button} onClick={() => perform(() => transition(task, "accepted"))}>{t.accept}</button>
              <button type="button" disabled={busy || !isLive} className={button} onClick={() => perform(() => transition(task, "rejected"))}>{t.reject}</button>
            </>}
            {task.status === "accepted" && <button type="button" disabled={busy || !isLive} className={button} onClick={() => perform(async () => { await api.deliverTask(task); setResult(null); })}>{t.deliver}</button>}
            {["approved", "dispatched", "accepted"].includes(task.status) && <button type="button" disabled={busy || !isLive} className={button} onClick={() => perform(() => transition(task, "cancelled"))}>{t.cancel}</button>}
          </div>}
        </li>)}
      </ul>
      {!status?.tasks.length && <p className="text-sm text-ink-2">{t.noTasks}</p>}
    </Card>
    <Card title={t.events}>
      <div className="overflow-x-auto"><table className="w-full text-left text-xs">
        <thead><tr>{[t.agent, t.kind, t.status, t.attempts, t.failureDetails].map(label => <th className="p-2" key={label}>{label}</th>)}</tr></thead>
        <tbody>{status?.events.map(event => <tr key={event.id} className="border-t border-line">
          <td className="p-2">{event.agent_id}<div className="text-muted">{event.received_at}</div></td>
          <td className="p-2">{event.kind}<div className="max-w-48 truncate text-muted" title={event.event_id}>{event.event_id}</div></td>
          <td className="p-2">{t[event.status]}</td><td className="p-2">{event.attempts}</td>
          <td className="p-2">{event.error}{event.status === "failed" && canOperate && <button type="button" className={button} disabled={busy || !isLive} onClick={() => perform(async () => { await api.retryEvent(event.id); })}>{t.retry}</button>}</td>
        </tr>)}</tbody>
      </table></div>
      {!status?.events.length && <p className="text-sm text-ink-2">{t.noEvents}</p>}
    </Card>
    {status && <Card title={t.drift}>
      <p className="text-sm">{t[status.drift.status]} · {t.samples}: {status.drift.sample_count}/{status.drift.minimum_samples} · {t.threshold}: {status.drift.threshold * 100}%</p>
      <p className="mt-2 text-xs text-muted">{t.driftNote}</p>
    </Card>}
    {status && <Card title={t.models}>
      <p className="mb-3 text-sm">{t.active}: <strong>{status.active_model}</strong></p>
      {status.models.map(model => <details key={model.version} className="mb-2 rounded border border-line p-3 text-xs">
        <summary>{model.version} · {t.cutoff}: {model.training_cutoff}</summary>
        <p className="mt-2 break-all">SHA256: {model.binary_sha256}</p>
        <pre className="mt-2 overflow-x-auto">{JSON.stringify(model.evaluation, null, 2)}</pre>
      </details>)}
    </Card>}
    {canOperate && <Card title={t.payload}>
      <p className="mb-2 text-xs text-muted">{t.manualHint}</p>
      <textarea className={`${input} min-h-36 w-full font-mono`} aria-label={t.payload} value={payload} onChange={e => setPayload(e.target.value)} />
      <button type="button" className={button} disabled={busy || !isLive || !payload.trim()} onClick={() => perform(async () => {
        await api.integrationEvent(JSON.parse(payload) as IntegrationEvent); setResult(null);
      })}>{t.submit}</button>
    </Card>}
  </div>;
}
