import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { Card, ErrorBox, Loading } from "../components/ui";
import { useApp } from "../lib/state";

export function Login() {
  const { t, health, authStatus, session, signIn } = useApp();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const from: unknown = (location.state as { from?: unknown } | null)?.from;
  const destination = typeof from === "string" && from.startsWith("/") && !from.startsWith("//") && !from.startsWith("/login") ? from : "/";
  const demo = (session?.auth_mode ?? health?.auth_mode) === "demo" && authStatus !== "offline";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    if (!demo && (!username.trim() || !password)) { setError(t.credentialsRequired); return; }
    setBusy(true);
    setError(null);
    try {
      await signIn(demo ? "" : username, demo ? "" : password);
      setPassword("");
      navigate(destination, { replace: true });
    } catch (e) {
      setError(e instanceof ApiError && (e.code === "unauthorized" || e.message === "Invalid username or password") ? t.signInFailed
        : e instanceof ApiError && e.code === "auth_api_outdated" ? t.authApiOutdated
        : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (authStatus === "loading") return <Loading text={t.loading} />;
  return (
    <div className="mx-auto max-w-3xl space-y-5 py-8">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{session ? t.account : t.signInTitle}</h1>
        <p className="mt-2 text-sm text-ink-2">{demo ? t.demoAuthNote : t.signInNote}</p>
      </div>
      {session ? (
        <Card title={t.signedInAs}>
          <p className="break-all font-medium text-ink">{session.subject} <span className="ml-2 rounded border border-line px-2 py-0.5 text-xs">{t[session.role]}</span></p>
          <Link to={destination} className="mt-4 inline-block rounded-md bg-accent px-4 py-2 text-sm font-medium text-white">{t.openDashboard}</Link>
        </Card>
      ) : (
        <Card>
          {authStatus === "offline" && <p role="status" className="mb-4 text-sm text-ink-2">{t.offlineReadOnly}</p>}
          <form onSubmit={submit} className="space-y-4">
            {!demo && <div>
              <label htmlFor="username" className="mb-1.5 block text-sm font-medium text-ink">{t.username}</label>
              <input id="username" name="username" type="text" value={username} onChange={(e) => setUsername(e.target.value)}
                autoComplete="username" autoCapitalize="none" spellCheck={false} maxLength={64} required disabled={busy}
                className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink" />
              <label htmlFor="password" className="mb-1.5 mt-4 block text-sm font-medium text-ink">{t.password}</label>
              <div className="flex gap-2">
                <input id="password" name="password" type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password" maxLength={128} required disabled={busy}
                  className="min-w-0 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink" />
                <button type="button" onClick={() => setShowPassword((value) => !value)} aria-pressed={showPassword}
                  className="rounded-md border border-line px-3 py-2 text-xs text-ink-2">{showPassword ? t.hidePassword : t.showPassword}</button>
              </div>
              <p className="mt-2 text-xs text-muted">{t.sessionNote}</p>
            </div>}
            {error && <ErrorBox message={error} />}
            <button type="submit" disabled={busy} className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
              {busy ? t.signingIn : demo ? t.continueDemo : t.signIn}
            </button>
            {authStatus === "offline" && <Link to={destination} className="ml-3 text-sm text-ink-2 underline">{t.openDashboard}</Link>}
          </form>
        </Card>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        {(["viewer", "operator", "admin"] as const).map((role) => (
          <Card key={role} title={t[role]}><p className="text-sm text-ink-2">{t[`${role}Access`]}</p></Card>
        ))}
      </div>
      <p className="text-xs text-muted">{t.roleNote}</p>
    </div>
  );
}
