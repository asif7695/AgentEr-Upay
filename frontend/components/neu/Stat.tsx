"use client";
import type { ReactNode } from "react";
import { CountUp } from "./Gauge";
import { NeuCard, cx } from "./core";

/** KPI tile: label, count-up value, optional note + icon. */
export function NeuStat({ label, value, format, note, icon, tone = "ink", fill, className, progress, barColor = "var(--accent-fill)" }: {
  label: string; value: number; format: (n: number) => string; note?: ReactNode; icon?: ReactNode; tone?: "ink" | "high" | "watch" | "ok" | "accent";
  /** brand-filled tile (upay blue or yellow); the value then uses the tile's own text colour */
  fill?: "blue" | "yellow"; className?: string;
  /** optional 0..100 bar under the value (e.g. % of capacity), coloured by `barColor` */
  progress?: number; barColor?: string;
}) {
  const colors = { ink: "", high: "text-high", watch: "text-watch", ok: "text-ok", accent: "text-accent" };
  return (
    <NeuCard variant={fill ?? "raised"} lift={!fill} className={cx("flex flex-col gap-2", className)}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-bold uppercase tracking-wide text-muted">{label}</span>
        {icon && <span className={cx("grid h-9 w-9 shrink-0 place-items-center rounded-xl", fill ? "bg-white/90 text-brand-ink" : "neu-inset-sm text-accent")} aria-hidden>{icon}</span>}
      </div>
      <CountUp value={value} format={format} className={cx("text-3xl font-extrabold leading-tight", !fill && colors[tone])} />
      {progress != null && (
        <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--hairline)" }} aria-hidden>
          <div className="h-full rounded-full" style={{ width: `${Math.max(2, Math.min(100, progress))}%`, background: barColor }} />
        </div>
      )}
      {note && <div className="text-xs text-muted">{note}</div>}
    </NeuCard>
  );
}
