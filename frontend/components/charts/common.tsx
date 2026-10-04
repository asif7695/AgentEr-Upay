"use client";
import type { ReactNode } from "react";
import { NeuCard, cx } from "@/components/neu";

export const AXIS = { stroke: "var(--hairline)", tick: { fill: "var(--muted)", fontSize: 12 } } as const;
export const GRID = { stroke: "var(--hairline)", strokeDasharray: "3 5", vertical: false, opacity: 0.8 } as const;

/** Soft rounded container: title, legend row, inset plot area. */
export function ChartCard({ title, subtitle, legend, children, className, footer }: {
  title: string; subtitle?: string; legend?: ReactNode; children: ReactNode; className?: string; footer?: ReactNode;
}) {
  return (
    <NeuCard className={cx("flex flex-col gap-3", className)}>
      <div>
        <h3 className="text-base font-bold">{title}</h3>
        {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
      </div>
      {legend && <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs font-medium">{legend}</div>}
      <div className="neu-inset p-2 pt-4">{children}</div>
      {footer && <div className="text-xs text-muted">{footer}</div>}
    </NeuCard>
  );
}

type Swatch = "line" | "dash" | "band" | "band-strong" | "closed" | "diamond" | "dot";
export function LegendItem({ kind, color, label }: { kind: Swatch; color: string; label: string }) {
  let mark: ReactNode;
  if (kind === "line") mark = <span className="inline-block h-0.5 w-5 rounded" style={{ background: color }} />;
  else if (kind === "dash") mark = <span className="inline-block w-5 border-t-2 border-dashed" style={{ borderColor: color }} />;
  else if (kind === "band") mark = <span className="inline-block h-3 w-5 rounded-sm" style={{ background: color, opacity: 0.45 }} />;
  else if (kind === "band-strong") mark = <span className="inline-block h-3 w-5 rounded-sm" style={{ background: color, opacity: 0.8 }} />;
  else if (kind === "closed") mark = <span className="inline-block h-3 w-5 rounded-sm" style={{ background: "var(--closed)", border: "1px solid var(--hairline)" }} />;
  else if (kind === "diamond") mark = <span className="inline-block h-2.5 w-2.5 rotate-45" style={{ background: color, border: "1.5px solid var(--text)" }} />;
  else mark = <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color, border: "2px solid var(--surface)", boxShadow: `0 0 0 1px ${color}` }} />;
  return <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-flex w-5 justify-center">{mark}</span><span>{label}</span></span>;
}

export function TipBox({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="neu-raised-sm min-w-44 p-3 text-xs" style={{ borderRadius: 10 }}>
      <div className="mb-1.5 text-sm font-bold">{title}</div>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  );
}
export function TipRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="inline-flex items-center gap-1.5 text-muted">{color && <span aria-hidden className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />}{label}</span>
      <span className="tabular font-semibold">{value}</span>
    </div>
  );
}

export const compact = (fmtNum: (n: number, f?: number) => string) => (n: number) => (Math.abs(n) >= 1000 ? `${fmtNum(n / 1000, n % 1000 === 0 ? 0 : 1)}k` : fmtNum(n));
