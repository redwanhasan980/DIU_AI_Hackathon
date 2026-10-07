import { api } from "../api/client";
import { Card, ErrorBox, Loading } from "../components/ui";
import { num, pct, takaShort } from "../lib/format";
import { useApi, useApp } from "../lib/state";

export function Validation() {
  const { t, lang } = useApp();
  const result = useApi(() => api.validationReport(), []);
  if (result.error) return <ErrorBox message={result.error} />;
  if (!result.data) return <Loading text={t.loading} />;
  const { validation: v, scale } = result.data;
  const table = "w-full text-sm tabular [&_th]:text-left [&_th]:pb-2 [&_td]:py-2 [&_td]:pr-4 [&_tr]:border-b [&_tr]:border-line";
  return <div className="space-y-4">
    <h1 className="text-xl font-semibold">{t.validationTitle}</h1>
    <Card title={t.assumption}><p className="text-sm text-ink-2">{t.validationNote}</p></Card>
    {!v && <p>{t.validationMissing}</p>}
    {v && <>
      <Card title={t.calibrationTitle} subtitle={`${v.calibration_period.join(" → ")} / ${v.assessment_period.join(" → ")} · ${t.calibrationTarget}`}>
        <div className="overflow-x-auto"><table className={table}>
          <thead><tr><th>{t.area}</th><th>{t.calibrationRaw}</th><th>{t.calibrationAdjusted}</th><th>{t.intervalWidth}</th></tr></thead>
          <tbody>{["overall", "event_days", "normal_days"].map((slice) => {
            const raw = v.calibration.raw.cashout[slice];
            const adjusted = v.calibration.calibrated.cashout[slice];
            return <tr key={slice}><td>{slice.replaceAll("_", " ")}</td><td>{pct(raw.coverage, lang, 1)}</td><td>{pct(adjusted.coverage, lang, 1)}</td><td>{takaShort(raw.width_bdt, lang)} → {takaShort(adjusted.width_bdt, lang)}</td></tr>;
          })}</tbody>
        </table></div>
      </Card>
      <Card title={t.featureAblations}>
        <div className="overflow-x-auto"><table className={table}>
          <thead><tr><th>{t.drivers}</th><th>WAPE</th><th>Event WAPE</th><th>Δ WAPE</th></tr></thead>
          <tbody>{Object.entries(v.feature_ablations).map(([name, row]) => <tr key={name}>
            <td>{name.replaceAll("_", " ")}</td><td>{pct(row.metrics.cashout.overall.wape, lang, 1)}</td>
            <td>{pct(row.metrics.cashout.event_days.wape, lang, 1)}</td>
            <td>{pct(row.metrics.cashout.overall.wape - v.calibration.raw.cashout.overall.wape, lang, 1)}</td>
          </tr>)}</tbody>
        </table></div>
      </Card>
      <Card title={t.pipelineAblations}>
        <div className="overflow-x-auto"><table className={table}>
          <thead><tr><th>{t.action}</th><th>{t.stockoutDays}</th><th>{t.failedValue}</th><th>{t.trips}</th><th>{t.cashHeld}</th></tr></thead>
          <tbody>{Object.entries(v.pipeline_ablations).map(([name, row]) => <tr key={name}>
            <td>{name.replaceAll("_", " ")}</td><td>{num(row.stockout_agent_days, lang)}</td>
            <td>{takaShort(row.failed_cashout_bdt + row.failed_cashin_bdt, lang)}</td><td>{num(row.rebalancing_trips, lang)}</td><td>{takaShort(row.avg_cash_held_bdt, lang)}</td>
          </tr>)}</tbody>
        </table></div>
      </Card>
      <Card title={t.robustnessTitle} subtitle={v.robustness.protocol}>
        <div className="overflow-x-auto"><table className={table}>
          <thead><tr><th>{t.assumption}</th><th>WAPE (CO)</th><th>Coverage (CO)</th><th>WAPE (CI)</th><th>Coverage (CI)</th></tr></thead>
          <tbody>{Object.entries(v.robustness.scenarios).map(([name, row]) => <tr key={name}>
            <td>{name.replaceAll("_", " ")}</td><td>{pct(row.cashout.overall.wape, lang, 1)}</td><td>{pct(row.cashout.overall.coverage, lang, 1)}</td>
            <td>{pct(row.cashin.overall.wape, lang, 1)}</td><td>{pct(row.cashin.overall.coverage, lang, 1)}</td>
          </tr>)}</tbody>
        </table></div>
      </Card>
      <Card title={t.sensitivityTitle} subtitle={t.syntheticImpactNote}>
        <div className="overflow-x-auto"><table className={table}>
          <thead><tr><th>{t.adherence}</th><th>{t.churnAssumption}</th><th>{t.stockoutDays}</th><th>{t.churnProxy}</th></tr></thead>
          <tbody>{v.business_sensitivity.map((row) => <tr key={`${row.compliance}-${row.churn_probability}`}>
            <td>{pct(row.compliance, lang)}</td><td>{pct(row.churn_probability, lang)}</td>
            <td>{num(row.stockout_agent_days, lang)}</td><td>{num(row.customers_at_risk, lang)}</td>
          </tr>)}</tbody>
        </table></div>
      </Card>
    </>}
    {scale && <Card title={t.benchmarkTitle} subtitle={scale.limitations}>
      <div className="overflow-x-auto"><table className={table}>
        <thead><tr><th>{t.agent}</th><th>{t.inferenceTime}</th><th>{t.planningTime}</th></tr></thead>
        <tbody>{scale.populations.map((row) => <tr key={row.n_agents}><td>{num(row.n_agents, lang)}</td>
          <td>{row.median_seconds.inference_seconds.toFixed(2)}</td><td>{row.median_seconds.planning_seconds.toFixed(2)}</td></tr>)}</tbody>
      </table></div>
    </Card>}
  </div>;
}
