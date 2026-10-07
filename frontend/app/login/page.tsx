"use client";
import { ChevronDown, LogIn, ShieldCheck, Store } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { NeuButton, NeuCard, NeuInput } from "@/components/neu";
import { Logo, Wordmark } from "@/components/shell/Logo";
import { LangButton, ThemeButton } from "@/components/shell/Toolbar";
import { ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/session";

const AGENT_IDS = Array.from({ length: 16 }, (_, i) => `A${String(i + 1).padStart(2, "0")}`);

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
  const asAgent = (id: string) => submit(undefined, { u: `Agent ${id}`, p: `agent${id.toLowerCase()}` });

  return (
    <div className="flex min-h-screen flex-col">
      <div className="brand-hero relative overflow-hidden rounded-b-[32px] border-b border-transparent px-4 pb-24 pt-4">
        {/* decorative upay-yellow disc */}
        <span aria-hidden className="pointer-events-none absolute -right-24 top-16 h-56 w-56 rounded-full" style={{ background: "var(--brand-yellow)" }} />
        <div className="relative mx-auto flex w-full max-w-md flex-col gap-8">
          <div className="on-brand flex justify-end gap-2"><LangButton /><ThemeButton /></div>
          <div className="flex flex-col gap-3">
            <Logo size={52} />
            <h1 className="text-3xl leading-tight"><Wordmark /></h1>
            <p className="hero-muted max-w-[16rem] text-sm font-medium">{t("app.tagline")}</p>
          </div>
        </div>
      </div>
      <main className="relative mx-auto -mt-16 flex w-full max-w-md flex-col gap-5 px-4 pb-10">
        <NeuCard className="flex flex-col gap-5">
          <div><h2 className="text-2xl font-extrabold">{t("login.title")}</h2><p className="text-sm text-muted">{t("login.sub")}</p></div>
          <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
            <NeuInput label={t("login.user")} placeholder={t("login.user.ph")} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
            <NeuInput label={t("login.pass")} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required error={error} />
            <NeuButton type="submit" variant="primary" loading={busy} icon={<LogIn size={18} aria-hidden />} disabled={!username || !password}>{t("login.submit")}</NeuButton>
          </form>
          <div className="flex flex-col gap-3 border-t pt-4" style={{ borderColor: "var(--border)" }}>
            <h3 className="text-center text-xs font-bold uppercase tracking-wide text-muted">{t("login.demo")}</h3>
            <div className="grid grid-cols-2 gap-3">
              <NeuButton variant="yellow" disabled={busy} icon={<Store size={17} aria-hidden />} onClick={() => asAgent("A01")}>{t("login.as_agent")}</NeuButton>
              <NeuButton disabled={busy} icon={<ShieldCheck size={17} aria-hidden />} onClick={() => submit(undefined, { u: "admin", p: "admin123" })}>{t("login.admin_short")}</NeuButton>
            </div>
            <p className="text-center text-xs text-muted">{t("login.demo.admin")} · {t("login.demo.agent")}</p>
            <details className="group">
              <summary className="flex min-h-11 cursor-pointer list-none items-center justify-center gap-1.5 rounded-xl text-sm font-bold text-accent">
                {t("login.agents")}<ChevronDown size={16} aria-hidden className="transition-transform group-open:rotate-180" />
              </summary>
              <div className="mt-2 grid grid-cols-4 gap-2">
                {AGENT_IDS.map((id) => (
                  <NeuButton key={id} disabled={busy} className="!px-2 text-sm" aria-label={`Agent ${id}`} onClick={() => asAgent(id)}>{id}</NeuButton>
                ))}
              </div>
            </details>
          </div>
        </NeuCard>
      </main>
    </div>
  );
}
