"use client";
import { Area, Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useI18n } from "@/lib/i18n";
import type { Bands, DayFc, RevealDay } from "@/lib/types";
import { AXIS, ChartCard, GRID, LegendItem, TipBox, TipRow, compact } from "./common";

/** P10 / P50 / P90 balance paths (same Monte Carlo as the risk numbers) against the buffer line. */
export function BalanceChart({ kind, dates, bands, buffer, bufferFrac, days, reveal, height = 250 }: {
  kind: "cash" | "efloat"; dates: string[]; bands: Bands; buffer: number; bufferFrac: number; days: DayFc[]; reveal?: RevealDay[] | null; height?: number;
}) {
  const { t, fmt } = useI18n();
  const color = kind === "cash" ? "var(--c-a)" : "var(--c-b)";
  const rows = dates.map((d, i) => {
    const closed = i === 0 ? 0 : days[i - 1].is_working_day ? 0 : 1;
    const rv = i > 0 ? reveal?.[i - 1] : undefined;
    return {
      label: i === 0 ? t("common.today") : fmt.axis(d), date: d, closed, p10: bands.p10[i], p50: bands.p50[i], p90: bands.p90[i], band: [bands.p10[i], bands.p90[i]],
      cf: rv ? (kind === "cash" ? rv.no_topup_cash : rv.no_topup_efloat) : i === 0 && reveal ? bands.p50[0] : undefined,
    };
  });
  const title = kind === "cash" ? t("fc.balance.cash") : t("fc.balance.efloat");
  const bufLabel = t("fc.balance.buffer", { pct: fmt.num(bufferFrac * 100) });
  const c = compact(fmt.num);
  const summary = rows.map((r) => `${r.label}: ${fmt.bdt(r.p50)} (${fmt.bdt(r.p10)} to ${fmt.bdt(r.p90)})`).join("; ");
  return (
    <ChartCard title={title} subtitle={t("fc.balance.note")}
      legend={<>
        <LegendItem kind="line" color={color} label={t("fc.balance.p50")} />
        <LegendItem kind="band" color={color} label={t("fc.balance.band")} />
        <LegendItem kind="dash" color="var(--high)" label={bufLabel} />
        <LegendItem kind="closed" color="" label={t("fc.closed")} />
        {reveal && <LegendItem kind="dash" color="var(--accent-2)" label={t("reveal.counterfactual")} />}
      </>}>
      <figure aria-label={title} className="m-0">
        <figcaption className="sr-only">{summary}</figcaption>
        <ResponsiveContainer width="100%" height={height} minWidth={0}>
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap={0}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: AXIS.stroke }} tick={AXIS.tick} interval={0} />
            <YAxis tickLine={false} axisLine={false} tick={AXIS.tick} width={46} tickFormatter={c}
              domain={[(m: number) => Math.min(0, Math.floor(m / 1000) * 1000), (m: number) => Math.ceil((m * 1.05) / 1000) * 1000]} />
            <YAxis yAxisId="bg" hide domain={[0, 1]} />
            <Bar yAxisId="bg" dataKey="closed" fill="var(--closed)" isAnimationActive={false} legendType="none" />
            <Area dataKey="band" stroke="none" fill={color} fillOpacity={0.24} isAnimationActive={false} activeDot={false} />
            <Line dataKey="p50" stroke={color} strokeWidth={2.5} dot={{ r: 3.5, fill: color, stroke: "var(--surface)", strokeWidth: 2 }}
              activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
            {reveal && <Line dataKey="cf" stroke="var(--accent-2)" strokeWidth={2.5} strokeDasharray="6 4" dot={false} isAnimationActive={false} activeDot={false} />}
            <ReferenceLine y={buffer} stroke="var(--high)" strokeDasharray="6 4" strokeWidth={2} />
            <ReferenceLine y={0} stroke="var(--hairline)" />
            <Tooltip cursor={{ stroke: "var(--muted)", strokeDasharray: "4 4" }} wrapperStyle={{ outline: "none", zIndex: 20 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const r = payload[0].payload as (typeof rows)[number];
                return (
                  <TipBox title={fmt.dateLong(r.date)}>
                    <TipRow label={t("fc.balance.p50")} value={fmt.bdt(r.p50)} color={color} />
                    <TipRow label={t("fc.balance.band")} value={`${fmt.bdt(r.p10)} – ${fmt.bdt(r.p90)}`} />
                    <TipRow label={bufLabel} value={fmt.bdt(buffer)} color="var(--high)" />
                    {r.cf !== undefined && <TipRow label={t("reveal.counterfactual")} value={fmt.bdt(r.cf)} color="var(--accent-2)" />}
                  </TipBox>
                );
              }} />
          </ComposedChart>
        </ResponsiveContainer>
      </figure>
    </ChartCard>
  );
}
