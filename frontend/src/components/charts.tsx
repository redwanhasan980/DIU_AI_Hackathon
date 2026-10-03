// Charts (Recharts). Mark specs follow the dataviz skill: 2px lines, thin bars with 4px rounded data
// ends, recessive grid, hover tooltips by default, legend for >= 2 series, text in ink tokens.
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Driver, Forecast, HistoryPoint, Lang, SweepPoint, TimelinePoint } from "../api/types";
import { STRINGS } from "../i18n/strings";
import { num, shortDate, taka, takaShort, toBnDigits } from "../lib/format";

const AXIS = { stroke: "var(--axis)", tickLine: false } as const;
const GRID = <CartesianGrid stroke="var(--grid)" strokeDasharray="0" vertical={false} />;

function TooltipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-semibold text-ink">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-ink-2">
            {r.color && <span className="inline-block h-2 w-2 rounded-full" style={{ background: r.color }} />}
            {r.label}
          </span>
          <span className="tabular font-medium text-ink">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

const legendStyle = { fontSize: 12, color: "var(--ink-2)", paddingTop: 8 };
// legend text wears ink, never the series colour (the swatch carries identity)
const legendText = (value: string) => <span style={{ color: "var(--ink-2)" }}>{value}</span>;

// ---- Forecast band ------------------------------------------------------------------------

interface FRow {
  date: string;
  observed?: number;
  stockout?: number;
  p50?: number;
  band?: [number, number];
  truth?: number;
}

export function ForecastChart({ history, forecast, side, lang }: {
  history: HistoryPoint[];
  forecast: Forecast;
  side: "cashout" | "cashin";
  lang: Lang;
}) {
  const t = STRINGS[lang];
  const rows: FRow[] = history.map((h) => {
    const v = side === "cashout" ? h.cashout_amt : h.cashin_amt;
    const so = side === "cashout" ? h.stockout_cash : h.stockout_efloat;
    return { date: h.date, observed: v, stockout: so ? v : undefined };
  });
  // join the forecast to the last observed point so the band starts where history ends
  const last = rows[rows.length - 1];
  if (last) {
    last.p50 = last.observed;
    last.band = [last.observed ?? 0, last.observed ?? 0];
  }
  for (const p of forecast.points) {
    const q = p[side];
    const truth = side === "cashout" ? p.actual_cashout : p.actual_cashin;
    rows.push({ date: p.date, p50: q.p50, band: [q.p10, q.p90], truth: truth ?? undefined });
  }
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 4 }}>
        {GRID}
        <XAxis dataKey="date" {...AXIS} tickFormatter={(d: string) => shortDate(d, lang)} minTickGap={24} />
        <YAxis {...AXIS} width={56} tickFormatter={(v: number) => takaShort(v, lang)} />
        <ReferenceLine x={forecast.origin} stroke="var(--axis)" strokeDasharray="4 4" />
        <Tooltip
          cursor={{ stroke: "var(--axis)" }}
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const r = payload[0].payload as FRow;
            const rows2 = [];
            if (r.observed !== undefined) rows2.push({ label: t.observed, value: taka(r.observed, lang), color: "var(--ink-2)" });
            if (r.stockout !== undefined) rows2.push({ label: "Stockout", value: "▲", color: "var(--critical)" });
            if (r.band && r.observed === undefined) {
              rows2.push({ label: t.p50, value: taka(r.p50 ?? 0, lang), color: "var(--series-1)" });
              rows2.push({ label: t.band, value: `${takaShort(r.band[0], lang)} – ${takaShort(r.band[1], lang)}` });
            }
            if (r.truth !== undefined) rows2.push({ label: t.truth, value: taka(r.truth, lang), color: "var(--ink)" });
            return <TooltipBox title={shortDate(String(label), lang)} rows={rows2} />;
          }}
        />
        <Legend wrapperStyle={legendStyle} iconSize={10} formatter={legendText} />
        <Area dataKey="band" name={t.band} stroke="none" fill="var(--series-1-band)" isAnimationActive={false} activeDot={false} legendType="square" />
        <Line dataKey="observed" name={t.observed} stroke="var(--ink-2)" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line dataKey="p50" name={t.p50} stroke="var(--series-1)" strokeWidth={2} strokeDasharray="5 3" dot={false} isAnimationActive={false} />
        <Scatter dataKey="truth" name={t.truth} fill="var(--ink)" shape="circle" isAnimationActive={false} />
        <Scatter dataKey="stockout" name={lang === "bn" ? "ঘাটতি (অপূর্ণ চাহিদা)" : "Stockout day"} fill="var(--critical)" shape="triangle" isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ---- SHAP drivers (diverging bars) ------------------------------------------------------------

export function DriversChart({ drivers, lang }: { drivers: Driver[]; lang: Lang }) {
  const t = STRINGS[lang];
  const data = drivers.map((d) => ({ ...d, name: `${d.label} (${d.value})` }));
  return (
    <div>
      <ResponsiveContainer width="100%" height={40 + data.length * 40}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 56, bottom: 4, left: 8 }} barCategoryGap={10}>
          <CartesianGrid stroke="var(--grid)" horizontal={false} />
          <XAxis type="number" {...AXIS} tickFormatter={(v: number) => takaShort(v, lang)}
            domain={[(min: number) => Math.min(0, min * 1.2), (max: number) => Math.max(0, max * 1.25)]} />
          <YAxis type="category" dataKey="name" width={210} {...AXIS} tick={{ fill: "var(--ink-2)", fontSize: 12 }} />
          <ReferenceLine x={0} stroke="var(--axis)" />
          <Tooltip
            cursor={{ fill: "var(--surface-2)" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as Driver & { name: string };
              const up = d.contribution_bdt >= 0;
              return (
                <TooltipBox
                  title={d.label}
                  rows={[
                    { label: lang === "bn" ? "মান" : "Value", value: d.value },
                    { label: up ? t.raises : t.lowers, value: taka(Math.abs(d.contribution_bdt), lang), color: up ? "var(--div-up)" : "var(--div-down)" },
                  ]}
                />
              );
            }}
          />
          <Bar dataKey="contribution_bdt" barSize={14} radius={4} isAnimationActive={false}
            label={(props: { x?: number | string; y?: number | string; width?: number | string; height?: number | string; value?: unknown }) => {
              const v = Number(props.value);
              const x = Number(props.x), w = Number(props.width), y = Number(props.y) + Number(props.height) / 2;
              // label just right of the bar's right end (for negative bars that is the zero line),
              // so it never collides with the category labels on the left
              const pos = v >= 0;
              const right = Math.max(x, x + w);
              return (
                <text x={right + 4} y={y} dy={4} fontSize={11} fill="var(--ink-2)" textAnchor="start">
                  {`${pos ? "+" : "−"}${takaShort(Math.abs(v), lang)}`}
                </text>
              );
            }}>
            {data.map((d) => (
              <Cell key={d.feature} fill={d.contribution_bdt >= 0 ? "var(--div-up)" : "var(--div-down)"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-1 flex gap-4 text-xs text-ink-2">
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--div-up)" }} />{t.raises}</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--div-down)" }} />{t.lowers}</span>
      </div>
    </div>
  );
}

// ---- Backtest timeline ------------------------------------------------------------------------

export function TimelineChart({ data, events, lang, metric }: {
  data: TimelinePoint[];
  events: { date: string; name: string }[];
  lang: Lang;
  metric: "stockouts" | "failed";
}) {
  const t = STRINGS[lang];
  const sq = metric === "stockouts" ? "status_quo_stockouts" : "status_quo_failed_bdt";
  const fw = metric === "stockouts" ? "floatwise_stockouts" : "floatwise_failed_bdt";
  const fmt = (v: number) => (metric === "stockouts" ? num(v, lang) : takaShort(v, lang));
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 16, right: 12, bottom: 0, left: 4 }}>
        {GRID}
        <XAxis dataKey="date" {...AXIS} tickFormatter={(d: string) => shortDate(d, lang)} minTickGap={36} />
        <YAxis {...AXIS} width={52} tickFormatter={fmt} />
        {events.map((e) => (
          <ReferenceLine key={e.date} x={e.date} stroke="var(--axis)" strokeDasharray="4 4"
            label={{ value: e.name, position: "insideTop", fill: "var(--muted)", fontSize: 11 }} />
        ))}
        <Tooltip
          cursor={{ stroke: "var(--axis)" }}
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const r = payload[0].payload as TimelinePoint;
            return (
              <TooltipBox
                title={shortDate(String(label), lang)}
                rows={[
                  { label: t.statusQuo, value: fmt(r[sq]), color: "var(--series-2)" },
                  { label: t.floatwise, value: fmt(r[fw]), color: "var(--series-1)" },
                ]}
              />
            );
          }}
        />
        <Legend wrapperStyle={legendStyle} iconSize={10} formatter={legendText} />
        <Line dataKey={sq} name={t.statusQuo} stroke="var(--series-2)" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line dataKey={fw} name={t.floatwise} stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ---- Service-level trade-off (two small charts: never a dual axis) ---------------------------------

export function SweepChart({ data, field, title, lang, baseline, current }: {
  data: SweepPoint[];
  field: "stockout_agent_days" | "avg_cash_held_bdt";
  title: string;
  lang: Lang;
  baseline: number;
  current: number;
}) {
  const t = STRINGS[lang];
  // cash varies in a narrow band across service levels, so show two decimals of a lakh
  const fmt = (v: number) =>
    field === "stockout_agent_days" ? num(v, lang) : (lang === "bn" ? toBnDigits(`৳${(v / 1e5).toFixed(2)}L`) : `৳${(v / 1e5).toFixed(2)}L`);
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-ink-2">{title}</div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 12, right: 12, bottom: 0, left: 4 }}>
          {GRID}
          <XAxis dataKey="service_level" {...AXIS} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} />
          <YAxis {...AXIS} width={52} tickFormatter={fmt} domain={["auto", "auto"]} />
          <ReferenceLine y={baseline} stroke="var(--series-2)" strokeDasharray="4 4"
            label={{ value: t.statusQuo, position: "insideTopRight", fill: "var(--ink-2)", fontSize: 11 }} />
          <ReferenceLine x={current} stroke="var(--axis)" />
          <Tooltip
            cursor={{ stroke: "var(--axis)" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0].payload as SweepPoint;
              return <TooltipBox title={`${t.serviceLevel} ${Math.round(r.service_level * 100)}%`}
                rows={[{ label: title, value: fmt(r[field]), color: "var(--series-1)" }]} />;
            }}
          />
          <Line dataKey={field} stroke="var(--series-1)" strokeWidth={2} dot={{ r: 4, fill: "var(--series-1)", stroke: "var(--surface-1)", strokeWidth: 2 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---- Before/after bars for segments ------------------------------------------------------------------

export function SegmentBars({ data, lang, labelOf }: {
  data: { segment: string; status_quo_stockouts: number; floatwise_stockouts: number }[];
  lang: Lang;
  labelOf: (s: string) => string;
}) {
  const t = STRINGS[lang];
  const rows = data.map((d) => ({ ...d, name: labelOf(d.segment) }));
  return (
    <ResponsiveContainer width="100%" height={60 + rows.length * 46}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 8 }} barGap={2} barCategoryGap={12}>
        <CartesianGrid stroke="var(--grid)" horizontal={false} />
        <XAxis type="number" {...AXIS} tickFormatter={(v: number) => num(v, lang)} />
        <YAxis type="category" dataKey="name" width={130} {...AXIS} tick={{ fill: "var(--ink-2)", fontSize: 12 }} />
        <Tooltip
          cursor={{ fill: "var(--surface-2)" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const r = payload[0].payload as (typeof rows)[number];
            return <TooltipBox title={r.name} rows={[
              { label: t.statusQuo, value: num(r.status_quo_stockouts, lang), color: "var(--series-2)" },
              { label: t.floatwise, value: num(r.floatwise_stockouts, lang), color: "var(--series-1)" },
            ]} />;
          }}
        />
        <Legend wrapperStyle={legendStyle} iconSize={10} formatter={legendText} />
        <Bar dataKey="status_quo_stockouts" name={t.statusQuo} fill="var(--series-2)" barSize={10} radius={4} isAnimationActive={false} />
        <Bar dataKey="floatwise_stockouts" name={t.floatwise} fill="var(--series-1)" barSize={10} radius={4} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
