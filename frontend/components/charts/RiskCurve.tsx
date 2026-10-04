"use client";
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useI18n } from "@/lib/i18n";
import type { Forecast } from "@/lib/types";
import { AXIS, ChartCard, GRID, LegendItem, TipBox, TipRow } from "./common";

/** 'Has run out by day k' for cash and e-float, with the coverage window and the HIGH/WATCH bands marked. */
export function RiskCurve({ fc, height = 230 }: { fc: Forecast; height?: number }) {
  const { t, fmt } = useI18n();
  const W = fc.cash.window_days;
  const rows = fc.days.map((d, i) => ({ label: fmt.axis(d.date), date: d.date, k: d.k, cash: fc.cash.risk_by_day[i], efloat: fc.efloat.risk_by_day[i] }));
  const summary = rows.map((r) => `${r.label}: ${t("term.cash")} ${fmt.pct(r.cash)}, ${t("term.efloat")} ${fmt.pct(r.efloat)}`).join("; ");
  return (
    <ChartCard title={t("fc.risk.curve")} subtitle={t("fc.window", { n: W, date: fmt.date(fc.cash.window_end_date) })}
      legend={<>
        <LegendItem kind="line" color="var(--c-a)" label={t("term.cash")} />
        <LegendItem kind="dash" color="var(--c-b)" label={t("term.efloat")} />
        <LegendItem kind="band" color="var(--muted)" label={t("fc.window", { n: W, date: fmt.dateTiny(fc.cash.window_end_date) })} />
      </>}>
      <figure aria-label={t("fc.risk.curve")} className="m-0">
        <figcaption className="sr-only">{summary}</figcaption>
        <ResponsiveContainer width="100%" height={height} minWidth={0}>
          <LineChart data={rows} margin={{ top: 8, right: 14, bottom: 0, left: 0 }}>
            <CartesianGrid {...GRID} />
            <ReferenceArea x1={rows[0].label} x2={rows[Math.min(W, rows.length) - 1].label} fill="var(--muted)" fillOpacity={0.12} ifOverflow="visible" />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: AXIS.stroke }} tick={AXIS.tick} interval={0} />
            <YAxis tickLine={false} axisLine={false} tick={AXIS.tick} width={40} domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v: number) => `${fmt.num(v)}%`} />
            <ReferenceLine y={fc.thresholds.high} stroke="var(--high)" strokeDasharray="5 5" />
            <ReferenceLine y={fc.thresholds.watch} stroke="var(--watch)" strokeDasharray="5 5" />
            <Line dataKey="cash" stroke="var(--c-a)" strokeWidth={2.5} dot={{ r: 4, fill: "var(--c-a)", stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
            <Line dataKey="efloat" stroke="var(--c-b)" strokeWidth={2.5} strokeDasharray="7 4" dot={{ r: 4, fill: "var(--c-b)", stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
            <Tooltip cursor={{ stroke: "var(--muted)", strokeDasharray: "4 4" }} wrapperStyle={{ outline: "none", zIndex: 20 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const r = payload[0].payload as (typeof rows)[number];
                return (
                  <TipBox title={`${t("fc.day", { n: r.k })} · ${fmt.dateLong(r.date)}`}>
                    <TipRow label={t("term.cash")} value={fmt.pct(r.cash, 1)} color="var(--c-a)" />
                    <TipRow label={t("term.efloat")} value={fmt.pct(r.efloat, 1)} color="var(--c-b)" />
                  </TipBox>
                );
              }} />
          </LineChart>
        </ResponsiveContainer>
      </figure>
    </ChartCard>
  );
}
