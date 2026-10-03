import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { isUsingFixtures } from "../api/client";
import { useApp } from "../lib/state";
import { Toggle } from "./ui";

export function Layout() {
  const { t, lang, setLang, theme, setTheme, date, setDate, health } = useApp();
  const [offline, setOffline] = useState(isUsingFixtures);
  useEffect(() => {
    const on = () => setOffline(true);
    window.addEventListener("fw-fixtures", on);
    return () => window.removeEventListener("fw-fixtures", on);
  }, []);
  const links = [
    { to: "/", label: t.nav.overview, end: true },
    { to: "/risk", label: t.nav.risk },
    { to: "/dso", label: t.nav.dso },
    { to: "/impact", label: t.nav.impact },
    { to: "/model", label: t.nav.model },
    { to: "/decisions", label: t.nav.decisions },
  ];
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-[1000] border-b border-line bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <div className="flex items-center gap-2">
            <span aria-hidden className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-lg font-bold text-white">৳</span>
            <div>
              <div className="text-base font-semibold leading-tight text-ink">FloatWise</div>
              <div className="text-[11px] leading-tight text-muted">{t.appTagline}</div>
            </div>
          </div>
          <nav className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto lg:order-none lg:w-auto">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm ${isActive ? "bg-surface-2 font-medium text-ink" : "text-ink-2 hover:text-ink"}`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-ink-2">
              {t.decisionDate}
              <input
                type="date"
                value={date}
                min={health?.forecast_start}
                max={health?.forecast_end}
                onChange={(e) => e.target.value && setDate(e.target.value)}
                className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink"
              />
            </label>
            <Toggle label="Language" value={lang} onChange={setLang} options={[{ value: "en", label: "EN" }, { value: "bn", label: "বাংলা" }]} />
            <Toggle
              label="Theme"
              value={theme}
              onChange={setTheme}
              options={[{ value: "system", label: "Auto" }, { value: "light", label: "☀" }, { value: "dark", label: "☾" }]}
            />
          </div>
        </div>
      </header>
      <div className="mx-auto max-w-7xl px-4 py-1.5 text-[11px] text-muted">
        <span className="mr-2 rounded border border-dashed border-line px-1.5 py-0.5">{t.syntheticBadge}</span>
        {offline && <span className="mr-2 rounded border border-[var(--warning)] px-1.5 py-0.5 text-ink">{t.fixturesBadge}</span>}
        {health && <span>model {health.model_version} · LLM {health.llm_available ? "on" : "off (templates)"}</span>}
      </div>
      <main className="mx-auto max-w-7xl px-4 pb-16">
        <Outlet />
      </main>
    </div>
  );
}
