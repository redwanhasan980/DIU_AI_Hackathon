// App-wide state: decision date, language and theme. Per-viewer conveniences only (localStorage, guarded).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, api, isUsingFixtures, setSessionActive } from "../api/client";
import type { AuthSession, Health, Lang } from "../api/types";
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
  authStatus: "loading" | "signed_out" | "signed_in" | "offline";
  session: AuthSession | null;
  signIn: (username?: string, password?: string) => Promise<void>;
  signOut: () => Promise<void>;
  canDecide: boolean;
  canOperate: boolean;
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
  const [auth, setAuth] = useState<{ status: AppState["authStatus"]; session: AuthSession | null }>({ status: "loading", session: null });
  const authRevision = useRef(0);

  const clearSession = useCallback(() => {
    authRevision.current += 1;
    setSessionActive(false);
    setAuth({ status: "signed_out", session: null });
  }, []);

  const signOut = useCallback(async () => {
    await api.logout();
    clearSession();
  }, [clearSession]);

  const signIn = useCallback(async (username = "", password = "") => {
    const revision = ++authRevision.current;
    const session = username || password ? await api.login({ username: username.trim(), password }) : await api.authMe();
    if (revision !== authRevision.current) return;
    setSessionActive(true);
    setHealth((previous) => previous ? { ...previous, auth_mode: session.auth_mode } : previous);
    setAuth({ status: "signed_in", session });
  }, []);

  useEffect(() => {
    const revision = ++authRevision.current;
    let alive = true;
    const initialize = async () => {
      let health: Health | null = null;
      try { health = await api.health(); } catch { /* sign-in can retry the live API */ }
      if (!alive || revision !== authRevision.current) return;
      setHealth(health);
      {
        try {
          const session = await api.authMe();
          if (alive && revision === authRevision.current) {
            setSessionActive(true);
            setAuth({ status: "signed_in", session });
          }
          return;
        } catch (e) {
          if (!alive || revision !== authRevision.current) return;
          if (e instanceof ApiError && e.code === "offline" && isUsingFixtures()) {
            setAuth({ status: "offline", session: null });
            return;
          }
        }
      }
      setAuth({ status: "signed_out", session: null });
    };
    void initialize();
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    window.addEventListener("fw-auth-expired", clearSession);
    return () => window.removeEventListener("fw-auth-expired", clearSession);
  }, [clearSession]);
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
    () => ({ date, setDate, lang, setLang, theme, setTheme, health, t: STRINGS[lang],
      authStatus: auth.status, session: auth.session, signIn, signOut,
      canDecide: auth.session?.role === "operator" || auth.session?.role === "admin",
      canOperate: auth.session?.role === "admin" }),
    [date, setDate, lang, setLang, theme, setTheme, health, auth, signIn, signOut],
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
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const refresh = () => setRevision((r) => r + 1);
    window.addEventListener("fw-auth", refresh);
    window.addEventListener("fw-balances", refresh);
    return () => {
      window.removeEventListener("fw-auth", refresh);
      window.removeEventListener("fw-balances", refresh);
    };
  }, []);
  const key = JSON.stringify([deps, revision]);
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
