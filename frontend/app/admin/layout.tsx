"use client";
import { Bell, ChevronsLeft, ChevronsRight, Coins, FlaskConical, LayoutDashboard, SlidersHorizontal, Truck } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { cx } from "@/components/neu";
import { Guard } from "@/components/shell/Guard";
import { Logo } from "@/components/shell/Logo";
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
        <aside className={cx("sticky top-0 hidden h-screen shrink-0 flex-col gap-4 p-4 transition-[width] duration-200 lg:flex", collapsed ? "w-[92px]" : "w-64")} aria-label={t("nav.menu")}>
          <div className="neu-raised flex h-full flex-col gap-2 p-3">
            <div className="flex items-center gap-3 px-1 py-2">
              <Logo />
              {!collapsed && <div className="leading-tight"><div className="text-sm font-extrabold">{t("app.name")}</div><div className="text-xs text-muted">{t("nav.admin")}</div></div>}
            </div>
            <nav className="mt-2 flex flex-1 flex-col gap-1.5">
              {NAV.map(({ href, key, icon: Icon }) => {
                const active = isActive(href);
                return (
                  <Link key={href} href={href} aria-current={active ? "page" : undefined} title={collapsed ? t(key) : undefined}
                    className={cx("flex min-h-12 items-center gap-3 rounded-2xl px-3.5 text-sm font-bold transition-all duration-200", active ? "neu-inset text-accent" : "text-muted hover:text-ink")}>
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
        <div className="flex min-w-0 flex-1 flex-col gap-4 p-4 lg:pl-0">
          <header className="neu-raised flex flex-col gap-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3 lg:hidden"><Logo /><span className="text-sm font-extrabold">{t("app.name")}</span></div>
              <SimControls />
              <div className="ml-auto flex items-center gap-2"><LangButton /><ThemeButton /><LogoutButton compact /></div>
            </div>
          </header>
          <nav aria-label={t("nav.menu")} className="neu-scroll flex gap-2 overflow-x-auto lg:hidden">
            {NAV.map(({ href, key, icon: Icon }) => (
              <Link key={href} href={href} aria-current={isActive(href) ? "page" : undefined}
                className={cx("flex min-h-11 shrink-0 items-center gap-2 rounded-2xl px-4 text-sm font-bold", isActive(href) ? "neu-inset text-accent" : "neu-raised-sm")}>
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
