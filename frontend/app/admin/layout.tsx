"use client";
import { Bell, ChevronsLeft, ChevronsRight, Coins, FlaskConical, LayoutDashboard, SlidersHorizontal, Truck } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { cx } from "@/components/neu";
import { Guard } from "@/components/shell/Guard";
import { Logo, Wordmark } from "@/components/shell/Logo";
import { SimControls } from "@/components/shell/SimControls";
import { LangButton, LogoutButton, ThemeButton } from "@/components/shell/Toolbar";
import { useI18n } from "@/lib/i18n";

const NAV = [
  { href: "/admin", key: "nav.overview", icon: LayoutDashboard },
  { href: "/admin/dispatch", key: "nav.dispatch", icon: Truck },
  { href: "/admin/rules", key: "nav.rules", icon: SlidersHorizontal },
  { href: "/admin/model", key: "nav.model", icon: FlaskConical },
  { href: "/admin/economics", key: "nav.economics", icon: Coins },
  { href: "/admin/alerts", key: "nav.alerts", icon: Bell },
] as const;

export default function AdminLayout({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const path = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => { try { setCollapsed(localStorage.getItem("upay-sidebar") === "1"); } catch { /* storage unavailable */ } }, []);
  const toggle = () => setCollapsed((c) => { try { localStorage.setItem("upay-sidebar", c ? "0" : "1"); } catch { /* storage unavailable */ } return !c; });
  const isActive = (href: string) => (href === "/admin" ? path === "/admin" || path.startsWith("/admin/agents") : path.startsWith(href));
  return (
    <Guard role="admin">
      <div className="flex min-h-screen">
        <aside className={cx("sticky top-0 hidden h-screen shrink-0 flex-col p-3 transition-[width] duration-200 lg:flex", collapsed ? "w-[88px]" : "w-64")} aria-label={t("nav.menu")}>
          <div className="brand-side on-brand flex h-full flex-col gap-2 rounded-[20px] border border-transparent p-3">
            <div className="flex items-center gap-3 px-1 py-2">
              <Logo />
              {!collapsed && <div className="leading-tight"><Wordmark className="text-sm" /><div className="side-muted text-xs">{t("nav.admin")}</div></div>}
            </div>
            <nav className="mt-3 flex flex-1 flex-col gap-1.5">
              {NAV.map(({ href, key, icon: Icon }) => {
                const active = isActive(href);
                return (
                  <Link key={href} href={href} aria-current={active ? "page" : undefined} title={collapsed ? t(key) : undefined}
                    className={cx("side-link flex min-h-12 items-center gap-3 rounded-xl px-3.5 text-sm font-bold transition-colors duration-150", collapsed && "justify-center px-0")}>
                    <Icon size={20} aria-hidden className="shrink-0" />{!collapsed && <span>{t(key)}</span>}
                  </Link>
                );
              })}
            </nav>
            <button onClick={toggle} className="neu-btn w-full" aria-label={collapsed ? t("nav.expand") : t("nav.collapse")} aria-expanded={!collapsed}>
              {collapsed ? <ChevronsRight size={18} aria-hidden /> : <><ChevronsLeft size={18} aria-hidden />{t("nav.collapse")}</>}
            </button>
          </div>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col gap-4 p-4 lg:pl-1">
          <header className="neu-raised flex flex-col gap-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3 lg:hidden"><Logo /><Wordmark onLight className="text-sm" /></div>
              <SimControls />
              <div className="ml-auto flex items-center gap-2"><LangButton /><ThemeButton /><LogoutButton compact /></div>
            </div>
          </header>
          <nav aria-label={t("nav.menu")} className="neu-scroll flex gap-2 overflow-x-auto lg:hidden">
            {NAV.map(({ href, key, icon: Icon }) => (
              <Link key={href} href={href} aria-current={isActive(href) ? "page" : undefined}
                className="neu-raised-sm flex min-h-11 shrink-0 items-center gap-2 px-4 text-sm font-bold">
                <Icon size={16} aria-hidden />{t(key)}
              </Link>
            ))}
          </nav>
          <main className="flex-1 pb-8">{children}</main>
        </div>
      </div>
    </Guard>
  );
}
