"use client";
import { LogIn, ShieldCheck, Store } from "lucide-react";

const AGENT_IDS = Array.from({ length: 16 }, (_, i) => `A${String(i + 1).padStart(2, "0")}`);
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { NeuButton, NeuCard, NeuInput } from "@/components/neu";
import { Logo } from "@/components/shell/Logo";
import { LangButton, ThemeButton } from "@/components/shell/Toolbar";
import { ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/session";

export default function LoginPage() {
  const { t } = useI18n();
  const { user, ready, login } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && user) router.replace(user.role === "admin" ? "/admin" : "/agent");
  }, [ready, user, router]);

  const submit = async (e?: FormEvent, creds?: { u: string; p: string }) => {
    e?.preventDefault();
    const u = creds?.u ?? username, p = creds?.p ?? password;
    setBusy(true); setError(null);
    try {
      const me = await login(u, p);
      router.replace(me.role === "admin" ? "/admin" : "/agent");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? t("login.err") : err instanceof ApiError && err.status === 0 ? t("common.network") : t("common.error"));
    } finally { setBusy(false); }
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-5 px-4 py-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3"><Logo size={44} /><div><div className="text-xl font-extrabold">{t("app.name")}</div><div className="text-xs text-muted">{t("app.tagline")}</div></div></div>
        <div className="flex gap-2"><LangButton /><ThemeButton /></div>
      </div>
      <NeuCard className="flex flex-col gap-5">
        <div><h1 className="text-2xl font-extrabold">{t("login.title")}</h1><p className="text-sm text-muted">{t("login.sub")}</p></div>
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          <NeuInput label={t("login.user")} placeholder={t("login.user.ph")} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          <NeuInput label={t("login.pass")} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required error={error} />
          <NeuButton type="submit" variant="primary" loading={busy} icon={<LogIn size={18} aria-hidden />} disabled={!username || !password}>{t("login.submit")}</NeuButton>
        </form>
      </NeuCard>
      <NeuCard variant="inset" className="flex flex-col gap-3">
        <h2 className="text-xs font-bold uppercase tracking-wide text-muted">{t("login.demo")}</h2>
        <p className="text-xs text-muted">{t("login.demo.admin")} · {t("login.demo.agent")}</p>
        <NeuButton disabled={busy} icon={<ShieldCheck size={18} aria-hidden />} onClick={() => submit(undefined, { u: "admin", p: "admin123" })}>{t("login.as_admin")}</NeuButton>
        <h3 className="mt-1 text-xs font-bold text-muted">{t("login.agents")}</h3>
        <div className="grid grid-cols-4 gap-2">
          {AGENT_IDS.map((id) => (
            <NeuButton key={id} disabled={busy} className="!px-2 text-sm" aria-label={`Agent ${id}`} icon={<Store size={15} aria-hidden />} onClick={() => submit(undefined, { u: `Agent ${id}`, p: `agent${id.toLowerCase()}` })}>{id}</NeuButton>
          ))}
        </div>
      </NeuCard>
    </div>
  );
}
