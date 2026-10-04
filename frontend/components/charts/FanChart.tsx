"use client";
import { Area, Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useI18n } from "@/lib/i18n";
import type { DayFc, RevealDay } from "@/lib/types";
import { AXIS, ChartCard, GRID, LegendItem, TipBox, TipRow, compact } from "./common";

type Flow = "cashout" | "cashin";

/** P10-P90 / P25-P75 fan, median line, mean markers, closed-day shading and an optional Demo-reveal overlay. */
export function FanChart({ days, flow, reveal, height = 260 }: { days: DayFc[]; flow: Flow; reveal?: RevealDay[] | null; height?: number }) {
  const { t, fmt } = useI18n();
  const color = flow === "cashout" ? "var(--c-a)" : "var(--c-b)";
  const rows = days.map((d, i) => {
    const q = d[flow], rv = reveal?.[i];
    return {
      label: fmt.axis(d.date), date: d.date, closed: d.is_working_day ? 0 : 1, holiday: d.is_holiday,
      p10: q.p10, p25: q.p25, p50: q.p50, p75: q.p75, p90: q.p90, mean: q.mean, surge: q.p_surge,
      band80: [q.p10, q.p90], band50: [q.p25, q.p75],
      truth: rv ? (flow === "cashout" ? rv.true_cashout : rv.true_cashin) : undefined,
      served: rv ? (flow === "cashout" ? rv.served_cashout : rv.served_cashin) : undefined,
    };
  });
  const title = flow === "cashout" ? t("fc.cashout.title") : t("fc.cashin.title");
  const c = compact(fmt.num);
  const summary = days.map((d) => `${fmt.date(d.date)}: ${fmt.bdt(d[flow].p50)} (${fmt.bdt(d[flow].p10)} to ${fmt.bdt(d[flow].p90)})`).join("; ");
  return (
    <ChartCard title={title} subtitle={t("fc.uncertain")}
      legend={<>
        <LegendItem kind="line" color={color} label={t("fc.median")} />
        <LegendItem kind="dot" color={color} label={t("fc.mean")} />
        <LegendItem kind="band-strong" color={color} label={t("fc.band.50")} />
        <LegendItem kind="band" color={color} label={t("fc.band.80")} />
        <LegendItem kind="closed" color="" label={t("fc.closed")} />
        {reveal && <LegendItem kind="diamond" color="var(--accent-2)" label={t("reveal.true")} />}
      </>}>
      <figure aria-label={title} className="m-0">
        <figcaption className="sr-only">{summary}</figcaption>
        <ResponsiveContainer width="100%" height={height} minWidth={0}>
          <ComposedChart data={rows} margin={{ top: 6, right: 12, bottom: 0, left: 0 }} barCategoryGap={0}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: AXIS.stroke }} tick={AXIS.tick} interval={0} />
            <YAxis tickLine={false} axisLine={false} tick={AXIS.tick} width={46} tickFormatter={c} domain={[0, (m: number) => Math.ceil((m * 1.08) / 1000) * 1000]} />
            <YAxis yAxisId="bg" hide domain={[0, 1]} />
            <Bar yAxisId="bg" dataKey="closed" fill="var(--closed)" isAnimationActive={false} legendType="none" />
            <Area dataKey="band80" stroke="none" fill={color} fillOpacity={0.2} isAnimationActive={false} activeDot={false} />
            <Area dataKey="band50" stroke="none" fill={color} fillOpacity={0.34} isAnimationActive={false} activeDot={false} />
            <Line dataKey="p50" stroke={color} strokeWidth={2.5} dot={false} activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
            <Line dataKey="mean" stroke="none" dot={{ r: 4.5, fill: color, stroke: "var(--surface)", strokeWidth: 2 }} activeDot={false} isAnimationActive={false} />
            {reveal && (
              <Line dataKey="truth" stroke="none" isAnimationActive={false} activeDot={false}
                dot={(p: { cx?: number; cy?: number; index?: number }) => p.cx == null || p.cy == null ? <g key={p.index} /> :
                  <rect key={p.index} x={p.cx - 6} y={p.cy - 6} width={12} height={12} transform={`rotate(45 ${p.cx} ${p.cy})`} fill="var(--accent-2)" stroke="var(--text)" strokeWidth={1.5} />} />
            )}
            <Tooltip cursor={{ stroke: "var(--muted)", strokeDasharray: "4 4" }} wrapperStyle={{ outline: "none", zIndex: 20 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const r = payload[0].payload as (typeof rows)[number];
                return (
                  <TipBox title={fmt.dateLong(r.date)}>
                    <TipRow label={r.closed ? t("fc.closed_short") : t("fc.open")} value={r.holiday ? "★" : r.closed ? "–" : "✓"} />
                    <TipRow label={t("fc.median")} value={fmt.bdt(r.p50)} color={color} />
                    <TipRow label={t("fc.mean")} value={fmt.bdt(r.mean)} />
                    <TipRow label={t("fc.band.80")} value={`${fmt.bdt(r.p10)} – ${fmt.bdt(r.p90)}`} />
                    <TipRow label={t("fc.band.50")} value={`${fmt.bdt(r.p25)} – ${fmt.bdt(r.p75)}`} />
                    <TipRow label={t("fc.surge")} value={fmt.pct(r.surge * 100)} />
                    {r.truth !== undefined && <TipRow label={t("reveal.true")} value={fmt.bdt(r.truth)} color="var(--accent-2)" />}
                    {r.served !== undefined && <TipRow label={t("reveal.served")} value={fmt.bdt(r.served)} />}
                  </TipBox>
                );
              }} />
          </ComposedChart>
        </ResponsiveContainer>
      </figure>
    </ChartCard>
  );
}
