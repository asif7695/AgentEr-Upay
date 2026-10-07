"use client";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { CircleCheck, Eye, TriangleAlert, X } from "lucide-react";
import {
  createElement, useEffect, useId, useRef,
  type ButtonHTMLAttributes, type ElementType, type HTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TdHTMLAttributes, type ThHTMLAttributes,
} from "react";
import { useI18n } from "@/lib/i18n";
import type { Status } from "@/lib/types";

export const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");

/* ------------------------------------------------------------------ NeuCard */
interface CardProps extends HTMLAttributes<HTMLElement> {
  variant?: "raised" | "inset" | "flat" | "small" | "yellow" | "blue"; as?: ElementType; pad?: boolean; lift?: boolean;
}
export function NeuCard({ variant = "raised", as = "div", pad = true, lift = false, className, children, ...rest }: CardProps) {
  const base = { raised: "neu-raised", inset: "neu-inset", flat: "neu-flat", small: "neu-raised-sm", yellow: "card-yellow", blue: "card-blue" }[variant];
  return createElement(as, {
    className: cx(base, pad && "p-5", lift && "transition-colors duration-150 hover:border-[var(--muted)]", className), ...rest,
  }, children);
}

/* ---------------------------------------------------------------- NeuButton */
interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> { variant?: "default" | "primary" | "danger" | "yellow" | "ink"; loading?: boolean; icon?: ReactNode }
export function NeuButton({ variant = "default", loading, icon, className, children, disabled, type = "button", ...rest }: BtnProps) {
  return (
    <button type={type} className={cx("neu-btn", variant !== "default" && variant, className)} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <span aria-hidden className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : icon}
      {children}
    </button>
  );
}

/* ----------------------------------------------------------------- NeuInput */
interface InputProps extends InputHTMLAttributes<HTMLInputElement> { label?: string; error?: string | null; hint?: string }
export function NeuInput({ label, error, hint, id, className, ...rest }: InputProps) {
  const auto = useId(); const iid = id ?? auto;
  return (
    <div className={className}>
      {label && <label htmlFor={iid} className="mb-1.5 block text-sm font-semibold">{label}</label>}
      <input id={iid} className="neu-input" aria-invalid={!!error || undefined} aria-describedby={error ? `${iid}-err` : hint ? `${iid}-hint` : undefined} {...rest} />
      {hint && !error && <p id={`${iid}-hint`} className="mt-1 text-xs text-muted">{hint}</p>}
      {error && <p id={`${iid}-err`} role="alert" className="mt-1 text-sm font-medium text-high">{error}</p>}
    </div>
  );
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> { label?: string }
export function NeuSelect({ label, id, className, children, ...rest }: SelectProps) {
  const auto = useId(); const sid = id ?? auto;
  return (
    <div className={className}>
      {label && <label htmlFor={sid} className="mb-1.5 block text-sm font-semibold">{label}</label>}
      <select id={sid} className="neu-input appearance-none pr-10" {...rest}>{children}</select>
    </div>
  );
}

/* --------------------------------------------------------------- NeuToggle */
export function NeuToggle({ checked, onChange, label, className }: { checked: boolean; onChange: (v: boolean) => void; label: string; className?: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
      className={cx("flex min-h-11 items-center gap-3 rounded-2xl px-1 text-left text-sm font-semibold", className)}>
      <span className="neu-inset-sm relative inline-block h-7 w-12 shrink-0 rounded-full" aria-hidden>
        <span className="neu-raised-sm absolute top-0.5 h-6 w-6 rounded-full transition-all duration-200"
          style={{ left: checked ? "calc(100% - 26px)" : "2px", background: checked ? "var(--accent-fill)" : undefined, borderRadius: 9999 }} />
      </span>
      <span>{label}</span>
    </button>
  );
}

/* ---------------------------------------------------------------- NeuTabs */
export function NeuTabs<T extends string>({ tabs, value, onChange, label, className }: {
  tabs: { id: T; label: string; icon?: ReactNode }[]; value: T; onChange: (v: T) => void; label?: string; className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const n = tabs.length;
    const next = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i - 1 + n) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
    if (next >= 0) { e.preventDefault(); onChange(tabs[next].id); refs.current[next]?.focus(); }
  };
  return (
    <div role="tablist" aria-label={label} className={cx("neu-inset inline-flex gap-1 p-1.5", className)}>
      {tabs.map((tb, i) => (
        <button key={tb.id} ref={(el) => { refs.current[i] = el; }} role="tab" aria-selected={value === tb.id} tabIndex={value === tb.id ? 0 : -1}
          onClick={() => onChange(tb.id)} onKeyDown={(e) => onKey(e, i)}
          className={cx("flex min-h-11 items-center gap-2 rounded-xl px-4 text-sm font-semibold transition-all duration-200", value === tb.id ? "neu-raised-sm text-accent" : "text-muted hover:text-ink")}>
          {tb.icon}{tb.label}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- NeuBadge */
const STATUS_ICON = { HIGH: TriangleAlert, WATCH: Eye, OK: CircleCheck } as const;
const STATUS_COLOR = { HIGH: "var(--high)", WATCH: "var(--watch)", OK: "var(--ok)" } as const;
const STATUS_TEXT = { HIGH: "text-high", WATCH: "text-watch", OK: "text-ok" } as const;
const STATUS_PILL = { HIGH: "pill-high", WATCH: "pill-watch", OK: "pill-ok" } as const;
export const statusColor = (s: Status) => STATUS_COLOR[s];

/** Status is never colour-only: every badge has an icon and a text label. */
export function StatusBadge({ status, size = "md", label }: { status: Status; size?: "sm" | "md"; label?: string }) {
  const { t } = useI18n();
  const Icon = STATUS_ICON[status];
  return (
    <span className={cx("pill inline-flex items-center gap-1.5 font-bold", STATUS_PILL[status], STATUS_TEXT[status], size === "sm" ? "px-2.5 py-0.5 text-xs" : "px-3 py-1 text-sm")}>
      <Icon aria-hidden size={size === "sm" ? 14 : 16} strokeWidth={2.4} style={{ color: STATUS_COLOR[status] }} />
      {label ?? t(`status.${status}` as const)}
    </span>
  );
}

export function NeuBadge({ children, tone = "neutral", icon, className }: { children: ReactNode; tone?: "neutral" | "accent" | "ok" | "watch" | "high" | "ink"; icon?: ReactNode; className?: string }) {
  const tones = { neutral: "text-muted", accent: "pill-accent text-accent", ok: "pill-ok text-ok", watch: "pill-watch text-watch", high: "pill-high text-high", ink: "pill-ink" };
  return <span className={cx("pill inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-bold", tones[tone], className)}>{icon}{children}</span>;
}

/* ---------------------------------------------------------------- Skeleton */
export function Skeleton({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden className={cx("neu-skeleton", className)} {...rest} />;
}

/* -------------------------------------------------- NeuModal / NeuDrawer */
export function NeuModal({ open, onClose, title, children, side = "center", footer }: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; side?: "center" | "right"; footer?: ReactNode;
}) {
  const reduce = useReducedMotion();
  const { t } = useI18n();
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>("input,select,button,[tabindex]")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && panel.current) {   // simple focus trap
        const f = panel.current.querySelectorAll<HTMLElement>("a[href],button:not(:disabled),input,select,textarea,[tabindex]:not([tabindex='-1'])");
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); prev?.focus(); };
  }, [open, onClose]);
  const dur = reduce ? 0 : 0.2;
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex" style={{ justifyContent: side === "right" ? "flex-end" : "center", alignItems: side === "right" ? "stretch" : "center" }}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: dur }}>
          <div className="absolute inset-0 bg-black/35" onClick={onClose} aria-hidden />
          <motion.div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId}
            className={cx("neu-raised relative flex max-h-[92vh] flex-col overflow-hidden", side === "right" ? "h-full w-full max-w-md rounded-r-none" : "m-4 w-full max-w-lg")}
            initial={{ opacity: 0, x: side === "right" ? 40 : 0, y: side === "right" ? 0 : 16 }} animate={{ opacity: 1, x: 0, y: 0 }}
            exit={{ opacity: 0, x: side === "right" ? 40 : 0, y: side === "right" ? 0 : 16 }} transition={{ duration: dur }}>
            <div className="flex items-center justify-between gap-4 p-5 pb-3">
              <h2 id={titleId} className="text-lg font-bold">{title}</h2>
              <button className="neu-btn !px-0" onClick={onClose} aria-label={t("common.close")}><X size={18} aria-hidden /></button>
            </div>
            <div className="neu-scroll flex-1 overflow-y-auto px-5 pb-5">{children}</div>
            {footer && <div className="flex justify-end gap-3 p-5 pt-3">{footer}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ---------------------------------------------------------------- NeuTable */
/** Flat rows with inset hover; only the table container carries a shadow (no heavy shadow per row). */
export function NeuTable({ children, className, caption }: { children: ReactNode; className?: string; caption?: string }) {
  return (
    <div className={cx("neu-inset neu-scroll overflow-x-auto p-2", className)}>
      <table className="w-full min-w-max border-separate border-spacing-y-0.5 text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        {children}
      </table>
    </div>
  );
}
export const Th = ({ children, className, ...rest }: ThHTMLAttributes<HTMLTableCellElement>) =>
  <th scope="col" className={cx("whitespace-nowrap px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wide text-muted", className)} {...rest}>{children}</th>;
export const Td = ({ children, className, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) =>
  <td className={cx("px-3 py-2.5 align-middle", className)} {...rest}>{children}</td>;
export const Tr = ({ children, className, ...rest }: HTMLAttributes<HTMLTableRowElement>) =>
  <tr className={cx("neu-row", className)} {...rest}>{children}</tr>;

/* ------------------------------------------------------------- state blocks */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <NeuCard role="alert" className="flex flex-col items-start gap-3">
      <div className="flex items-center gap-2 font-semibold text-high"><TriangleAlert size={18} aria-hidden />{t("common.error")}</div>
      <p className="text-sm text-muted">{message}</p>
      {onRetry && <NeuButton onClick={onRetry}>{t("common.retry")}</NeuButton>}
    </NeuCard>
  );
}
export function EmptyState({ message }: { message: string }) {
  return <div className="neu-inset p-8 text-center text-sm text-muted">{message}</div>;
}
