"use client";
import { Languages, LogOut, Moon, Sun } from "lucide-react";
import { NeuButton, cx } from "@/components/neu";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/session";
import { useTheme } from "@/lib/theme";

export function ThemeButton() {
  const { resolved, cycle } = useTheme();
  const { t } = useI18n();
  return (
    <NeuButton onClick={cycle} aria-label={t("theme.toggle")} title={t("theme.toggle")} className="!px-0">
      {resolved === "dark" ? <Sun size={18} aria-hidden /> : <Moon size={18} aria-hidden />}
    </NeuButton>
  );
}

export function LangButton() {
  const { lang, setLang, t } = useI18n();
  return (
    <NeuButton onClick={() => setLang(lang === "en" ? "bn" : "en")} aria-label={t("lang.label")} icon={<Languages size={18} aria-hidden className="hidden sm:block" />}>
      {t("lang.toggle")}
    </NeuButton>
  );
}

export function LogoutButton({ compact }: { compact?: boolean }) {
  const { logout } = useAuth();
  const { t } = useI18n();
  return (
    <NeuButton onClick={logout} aria-label={t("nav.logout")} className={cx(compact && "!px-0")} icon={<LogOut size={18} aria-hidden />}>
      {!compact && t("nav.logout")}
    </NeuButton>
  );
}

export function SyntheticBanner({ className }: { className?: string }) {
  const { t } = useI18n();
  return (
    <p role="note" className={cx("neu-inset flex items-start gap-2 px-3 py-2 text-xs font-semibold text-muted", className)}>
      <span aria-hidden className="mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: "var(--accent-2)", boxShadow: "0 0 0 1.5px var(--text)" }} />
      {t("banner.synthetic")}
    </p>
  );
}
