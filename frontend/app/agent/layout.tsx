"use client";
import { ClipboardEdit, History, House, LineChart } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { cx } from "@/components/neu";
import { HeroCtx, type Hero } from "@/components/shell/AgentHero";
import { Guard } from "@/components/shell/Guard";
import { Logo, Wordmark } from "@/components/shell/Logo";
import { LangButton, LogoutButton, ThemeButton } from "@/components/shell/Toolbar";
import { useI18n } from "@/lib/i18n";
import { useAuth, useSim } from "@/lib/session";

const TABS = [
  { href: "/agent", key: "nav.home", icon: House },
  { href: "/agent/report", key: "nav.report", icon: ClipboardEdit },
  { href: "/agent/forecast", key: "nav.forecast", icon: LineChart },
  { href: "/agent/history", key: "nav.history", icon: History },
] as const;

export default function AgentLayout({ children }: { children: ReactNode }) {
  const { t, fmt } = useI18n();
  const { user } = useAuth();
  const { sim } = useSim();
  const path = usePathname();
  const [hero, setHero] = useState<Hero>(null);
  return (
    <Guard role="agent">
      <HeroCtx.Provider value={setHero}>
        <div className="flex min-h-screen w-full flex-col pb-28">
          <div className="brand-hero rounded-b-[28px] border-b border-transparent px-4 pt-4 md:px-6" style={{ paddingBottom: hero ? 64 : 20 }}>
            <header className="mx-auto flex w-full max-w-5xl items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2.5">
                <Logo size={34} />
                <div className="min-w-0 leading-tight">
                  <Wordmark className="text-sm" />
                  <div className="hero-muted truncate text-xs">{user?.display_name}{sim ? ` · ${fmt.date(sim.date)}` : ""}</div>
                </div>
              </div>
              <div className="on-brand flex shrink-0 items-center gap-1.5"><LangButton /><ThemeButton /><LogoutButton compact /></div>
            </header>
            {hero && (
              <div className="mx-auto mt-5 max-w-5xl text-center">
                <h1 className="text-2xl font-extrabold">{hero.title}</h1>
                {hero.sub && <p className="hero-muted mt-1 text-sm">{hero.sub}</p>}
              </div>
            )}
          </div>
          <main className={cx("relative mx-auto w-full max-w-5xl flex-1 px-4 md:px-6", hero ? "-mt-11" : "mt-5")}>{children}</main>
        </div>
        <nav aria-label={t("nav.menu")} className="neu-raised fixed inset-x-3 bottom-3 z-40 mx-auto flex max-w-xl justify-around p-1.5" style={{ borderRadius: 18 }}>
          {TABS.map(({ href, key, icon: Icon }) => {
            const active = path === href;
            return (
              <Link key={href} href={href} aria-current={active ? "page" : undefined}
                className={cx("flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 rounded-2xl px-2 text-[11px] font-bold transition-all duration-200", active ? "" : "text-muted hover:text-accent")}>
                <Icon size={20} aria-hidden />{t(key)}
              </Link>
            );
          })}
        </nav>
      </HeroCtx.Provider>
    </Guard>
  );
}
