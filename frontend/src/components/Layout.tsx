import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { isUsingFixtures } from "../api/client";
import { useApp } from "../lib/state";
import { Toggle } from "./ui";
import { INTEGRATION_STRINGS } from "../i18n/integration";

export function Layout() {
  const { t, lang, setLang, theme, setTheme, date, setDate, health, authStatus, session, signOut, canOperate } = useApp();
  const [offline, setOffline] = useState(isUsingFixtures);
  const [signingOut, setSigningOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const logout = async () => {
    setSigningOut(true);
    setLogoutError(null);
    try { await signOut(); } catch (e) { setLogoutError((e as Error).message); }
    finally { setSigningOut(false); }
  };
  useEffect(() => {
    const on = () => setOffline(isUsingFixtures());
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
    { to: "/validation", label: t.validationTitle },
    { to: "/integration", label: INTEGRATION_STRINGS[lang].title },
    ...(canOperate ? [{ to: "/operations", label: t.operationsTitle }] : []),
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
            {(authStatus === "signed_in" || authStatus === "offline") && links.map((l) => (
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
            {session && <>
              <span className="max-w-32 truncate text-xs text-ink-2" title={session.subject}>{session.subject}</span>
              <span className="rounded border border-line px-2 py-0.5 text-xs font-medium text-ink">{t[session.role]}</span>
            </>}
            <NavLink to="/login" className="rounded-md border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-2">
              {session ? t.account : t.signIn}
            </NavLink>
            {session && <button type="button" disabled={signingOut} onClick={logout} className="rounded-md border border-line px-3 py-1.5 text-xs text-ink-2 hover:bg-surface-2">{signingOut ? t.loading : t.signOut}</button>}
          </div>
        </div>
      </header>
      <div className="mx-auto max-w-7xl px-4 py-1.5 text-[11px] text-muted">
        <span className="mr-2 rounded border border-dashed border-line px-1.5 py-0.5">{t.syntheticBadge}</span>
        {offline && <span className="mr-2 rounded border border-[var(--warning)] px-1.5 py-0.5 text-ink">{t.fixturesBadge}</span>}
        {session?.auth_mode === "demo" && <span className="mr-2 rounded border border-line px-1.5 py-0.5">{t.demoAccess} · {t.admin}</span>}
        {health && <span>model {health.model_version} · LLM {health.llm_available ? "on" : "off (templates)"}</span>}
      </div>
      <main className="mx-auto max-w-7xl px-4 pb-16">
        {logoutError && <p role="alert" className="mb-4 text-sm text-ink">{logoutError}</p>}
        {authStatus === "offline" && <p role="status" className="mb-4 rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">{t.offlineReadOnly}</p>}
        <Outlet />
      </main>
    </div>
  );
}
