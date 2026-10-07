"use client";
import { animate, motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useI18n } from "@/lib/i18n";
import type { Status } from "@/lib/types";
import { StatusBadge, cx, statusColor } from "./core";

/** Animated number: counts up from the previous value (instant under prefers-reduced-motion). */
export function CountUp({ value, format, className }: { value: number; format: (n: number) => string; className?: string }) {
  const reduce = useReducedMotion();
  const [v, setV] = useState(reduce ? value : 0);
  const from = useRef(reduce ? value : 0);
  useEffect(() => {
    if (reduce) { setV(value); from.current = value; return; }
    const c = animate(from.current, value, { duration: 0.7, ease: "easeOut", onUpdate: (x) => { from.current = x; setV(x); } });
    return () => c.stop();
  }, [value, reduce]);
  return <span className={cx("tabular", className)}>{format(v)}</span>;
}

/** Flat radial gauge (270° arc). Sweeps on load; status = colour + icon + text. */
export function NeuGauge({ value, status, title, subtitle, thresholds = { watch: 30, high: 50 }, size = 176, footer }: {
  value: number; status: Status; title: string; subtitle?: string; thresholds?: { watch: number; high: number }; size?: number; footer?: ReactNode;
}) {
  const { fmt } = useI18n();
  const reduce = useReducedMotion();
  const stroke = 14, pad = 10;
  const r = (size - stroke) / 2 - pad, C = 2 * Math.PI * r, arc = 0.75 * C;
  const clamp = Math.max(0, Math.min(100, value));
  const tick = (pct: number) => {
    const ang = (135 + 270 * (pct / 100)) * (Math.PI / 180), cx0 = size / 2, cy0 = size / 2;
    const a = r - stroke / 2 - 3, b = r + stroke / 2 + 3;
    return { x1: cx0 + a * Math.cos(ang), y1: cy0 + a * Math.sin(ang), x2: cx0 + b * Math.cos(ang), y2: cy0 + b * Math.sin(ang) };
  };
  return (
    <figure className="flex w-full min-w-0 flex-col items-center gap-3 text-center" aria-label={`${title}: ${fmt.pct(value)}`}>
      <div className="relative grid w-full place-items-center rounded-full" style={{ maxWidth: size + 16, aspectRatio: "1 / 1", borderRadius: 9999 }}>
        <svg viewBox={`0 0 ${size} ${size}`} className="relative h-[92%] w-[92%]" role="img" aria-hidden>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--hairline)" strokeWidth={stroke} strokeLinecap="round"
            strokeDasharray={`${arc} ${C}`} transform={`rotate(135 ${size / 2} ${size / 2})`} />
          <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={statusColor(status)} strokeWidth={stroke} strokeLinecap="round"
            transform={`rotate(135 ${size / 2} ${size / 2})`}
            initial={{ strokeDasharray: `0 ${C}` }} animate={{ strokeDasharray: `${Math.max(0.001, arc * clamp / 100)} ${C}` }}
            transition={{ duration: reduce ? 0 : 1.0, ease: "easeOut" }} />
          {[thresholds.watch, thresholds.high].map((p) => <line key={p} {...tick(p)} stroke="var(--muted)" strokeWidth={2} strokeLinecap="round" opacity={0.7} />)}
        </svg>
        <div className="absolute grid place-items-center">
          <CountUp value={value} format={(n) => fmt.pct(n)} className="text-2xl font-extrabold leading-none sm:text-4xl" />
        </div>
      </div>
      <figcaption className="flex flex-col items-center gap-1.5">
        <span className="text-sm font-bold">{title}</span>
        <StatusBadge status={status} />
        {subtitle && <span className="max-w-[16rem] text-xs text-muted">{subtitle}</span>}
        {footer}
      </figcaption>
    </figure>
  );
}
