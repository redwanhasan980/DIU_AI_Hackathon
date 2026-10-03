import type { ReactNode } from "react";
import type { Action, Lang, RiskBand } from "../api/types";
import { ACTION_LABEL, BAND_LABEL } from "../i18n/strings";
import { pct } from "../lib/format";

export function Card({ title, subtitle, children, right, className = "" }: {
  title?: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-line bg-surface p-4 sm:p-5 ${className}`}>
      {(title || right) && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function Kpi({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "good" | "bad" }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="text-xs font-medium text-ink-2">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink">{value}</div>
      {sub && (
        <div
          className="mt-1 text-xs"
          style={{ color: tone === "good" ? "var(--good-text)" : tone === "bad" ? "var(--critical-text)" : "var(--muted)" }}
        >
          {sub}
        </div>
      )}
    </div>
  );
}

const BAND_STYLE: Record<RiskBand, { color: string; icon: string }> = {
  low: { color: "var(--good)", icon: "✓" },
  medium: { color: "var(--warning)", icon: "!" },
  high: { color: "var(--critical)", icon: "▲" },
};

/** Status is never colour-only: icon + label + colour (dataviz non-negotiable). */
export function RiskBadge({ band, p, lang }: { band: RiskBand; p?: number; lang: Lang }) {
  const s = BAND_STYLE[band];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-ink">
      <span
        aria-hidden
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold text-white"
        style={{ background: s.color, color: band === "medium" ? "#0b0b0b" : "#fff" }}
      >
        {s.icon}
      </span>
      {BAND_LABEL[lang][band]}
      {p !== undefined && <span className="tabular text-ink-2">{pct(p, lang)}</span>}
    </span>
  );
}

export function bandOf(p: number, threshold = 0.1): RiskBand {
  return p >= 0.5 ? "high" : p >= threshold ? "medium" : "low";
}

export function ActionBadge({ action, lang }: { action: Action; lang: Lang }) {
  const tone =
    action === "NO_ACTION"
      ? "border-line text-ink-2"
      : action === "NEEDS_EXTRA_FLOAT"
        ? "border-[var(--critical)] text-ink"
        : "border-[var(--accent)] text-ink";
  return (
    <span className={`inline-block whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-medium ${tone}`}>
      {action === "NEEDS_EXTRA_FLOAT" && "⚠ "}
      {ACTION_LABEL[lang][action]}
    </span>
  );
}

export function Loading({ text = "Loading…" }: { text?: string }) {
  return <div className="animate-pulse py-10 text-center text-sm text-muted">{text}</div>;
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div role="alert" className="rounded-lg border border-[var(--critical)] bg-surface p-4 text-sm text-ink">
      <strong className="mr-1">⚠</strong>
      {message}
    </div>
  );
}

export function Toggle<T extends string>({ value, options, onChange, label }: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
            value === o.value ? "bg-surface text-ink shadow-sm" : "text-ink-2 hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "accent" | "warn" }) {
  const cls =
    tone === "accent"
      ? "border-[var(--accent)] text-ink"
      : tone === "warn"
        ? "border-[var(--warning)] text-ink"
        : "border-line text-ink-2";
  return <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs ${cls}`}>{children}</span>;
}

/** Visually distinct "assumption" marker (R-AI-5: separate predictions / assumptions / generated text). */
export function AssumptionTag({ label = "Assumption" }: { label?: string }) {
  return (
    <span className="ml-1 rounded border border-dashed border-line px-1 text-[10px] uppercase tracking-wide text-muted">
      {label}
    </span>
  );
}
