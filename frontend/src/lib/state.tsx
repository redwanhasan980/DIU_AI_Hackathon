// App-wide state: decision date, language and theme. Per-viewer conveniences only (localStorage, guarded).
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { Health, Lang } from "../api/types";
import { STRINGS } from "../i18n/strings";

type Theme = "system" | "light" | "dark";

interface AppState {
  date: string;
  setDate: (d: string) => void;
  lang: Lang;
  setLang: (l: Lang) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  health: Health | null;
  t: (typeof STRINGS)["en"];
}

const Ctx = createContext<AppState | null>(null);
export const DEMO_DATE = "2026-03-15";

function load<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T | null) ?? fallback;
  } catch {
    return fallback;
  }
}
function save(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: keep in memory only */
  }
}

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [date, setDateRaw] = useState<string>(() => new URLSearchParams(location.search).get("date") ?? DEMO_DATE);
  const [lang, setLangRaw] = useState<Lang>(() => load<Lang>("fw.lang", "en"));
  const [theme, setThemeRaw] = useState<Theme>(() => load<Theme>("fw.theme", "system"));
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api.health().then(setHealth, () => setHealth(null));
  }, []);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangRaw(l);
    save("fw.lang", l);
  }, []);
  const setTheme = useCallback((t: Theme) => {
    setThemeRaw(t);
    save("fw.theme", t);
  }, []);
  const setDate = useCallback((d: string) => setDateRaw(d), []);

  const value = useMemo(
    () => ({ date, setDate, lang, setLang, theme, setTheme, health, t: STRINGS[lang] }),
    [date, setDate, lang, setLang, theme, setTheme, health],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside provider");
  return v;
}

/** Fetch helper: re-runs when deps change; ignores stale responses. Loading = no result for the current deps yet. */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[]) {
  const key = JSON.stringify(deps);
  const [state, setState] = useState<{ key: string | null; data: T | null; error: string | null }>({
    key: null,
    data: null,
    error: null,
  });
  useEffect(() => {
    let alive = true;
    fn().then(
      (data) => alive && setState({ key, data, error: null }),
      (e: Error) => alive && setState({ key, data: null, error: e.message }),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const loading = state.key !== key;
  return { data: loading ? null : state.data, error: loading ? null : state.error, loading };
}
