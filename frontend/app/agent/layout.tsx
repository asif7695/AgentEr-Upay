"use client";
import { ClipboardEdit, History, House, LineChart } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { cx } from "@/components/neu";
import { Guard } from "@/components/shell/Guard";
import { Logo } from "@/components/shell/Logo";
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
  return (
    <Guard role="agent">
      <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 pb-28 pt-4 md:px-6">
        <header className="mb-4 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <Logo size={32} />
            <div className="min-w-0 leading-tight">
              <div className="text-sm font-extrabold">{t("app.name")}</div>
              <div className="truncate text-xs text-muted">{user?.display_name}{sim ? ` · ${fmt.date(sim.date)}` : ""}</div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5"><LangButton /><ThemeButton /><LogoutButton compact /></div>
        </header>
        <main className="flex-1">{children}</main>
      </div>
      <nav aria-label={t("nav.menu")} className="neu-raised fixed inset-x-3 bottom-3 z-40 mx-auto flex max-w-xl justify-around p-1.5" style={{ borderRadius: 14 }}>
        {TABS.map(({ href, key, icon: Icon }) => {
          const active = path === href;
          return (
            <Link key={href} href={href} aria-current={active ? "page" : undefined}
              className={cx("flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 rounded-2xl px-2 text-[11px] font-bold transition-all duration-200", active ? "neu-inset text-accent" : "text-muted hover:text-ink")}>
              <Icon size={20} aria-hidden />{t(key)}
            </Link>
          );
        })}
      </nav>
    </Guard>
  );
}
