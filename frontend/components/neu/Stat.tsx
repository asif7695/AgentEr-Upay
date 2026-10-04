"use client";
import type { ReactNode } from "react";
import { CountUp } from "./Gauge";
import { NeuCard, cx } from "./core";

/** KPI tile: label, count-up value, optional note + icon. */
export function NeuStat({ label, value, format, note, icon, tone = "ink", className }: {
  label: string; value: number; format: (n: number) => string; note?: ReactNode; icon?: ReactNode; tone?: "ink" | "high" | "watch" | "ok" | "accent"; className?: string;
}) {
  const colors = { ink: "", high: "text-high", watch: "text-watch", ok: "text-ok", accent: "text-accent" };
  return (
    <NeuCard lift className={cx("flex flex-col gap-2", className)}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-bold uppercase tracking-wide text-muted">{label}</span>
        {icon && <span className="neu-inset-sm grid h-9 w-9 shrink-0 place-items-center text-muted" aria-hidden>{icon}</span>}
      </div>
      <CountUp value={value} format={format} className={cx("text-3xl font-extrabold leading-tight", colors[tone])} />
      {note && <div className="text-xs text-muted">{note}</div>}
    </NeuCard>
  );
}
