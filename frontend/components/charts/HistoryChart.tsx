"use client";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useI18n } from "@/lib/i18n";
import type { HistoryRow } from "@/lib/types";
import { AXIS, ChartCard, GRID, LegendItem, TipBox, TipRow, compact } from "./common";

type DotProps = { cx?: number; cy?: number; index?: number; payload?: HistoryRow };
const Tri = ({ x, y }: { x: number; y: number }) => <path d={`M${x} ${y - 7}L${x + 6.5} ${y + 5}L${x - 6.5} ${y + 5}Z`} fill="var(--ok)" stroke="var(--text)" strokeWidth={1.2} />;
const Cross = ({ x, y }: { x: number; y: number }) => <path d={`M${x - 5.5} ${y - 5.5}L${x + 5.5} ${y + 5.5}M${x + 5.5} ${y - 5.5}L${x - 5.5} ${y + 5.5}`} stroke="var(--high)" strokeWidth={3} strokeLinecap="round" />;

/** Closing balances over time. Top-up arrivals (triangle) and stock-out days (cross) are marked on the line they belong to. */
export function HistoryChart({ rows, capacityCash }: { rows: HistoryRow[]; capacityCash: number }) {
  const { t, fmt } = useI18n();
  const c = compact(fmt.num);
  const dot = (kind: "cash" | "efloat") => function MarkerDot(p: DotProps) {
    const r = p.payload; const key = String(p.index);
    if (p.cx == null || p.cy == null || !r) return <g key={key} />;
    const so = kind === "cash" ? r.cash_stockout : r.efloat_stockout;
    const tu = (kind === "cash" ? r.cash_topup : r.efloat_topup) > 0;
    return <g key={key}>{tu && <Tri x={p.cx} y={p.cy} />}{so && <Cross x={p.cx} y={p.cy} />}</g>;
  };
  const data = rows.map((r) => ({ ...r, label: fmt.dateTiny(r.date) }));
  return (
    <ChartCard title={t("hist.balances")}
      legend={<>
        <LegendItem kind="line" color="var(--c-a)" label={t("hist.cash")} />
        <LegendItem kind="dash" color="var(--c-b)" label={t("hist.efloat")} />
        <span className="inline-flex items-center gap-1.5"><svg width="16" height="14" aria-hidden><Tri x={8} y={8} /></svg>{t("hist.topup")}</span>
        <span className="inline-flex items-center gap-1.5"><svg width="16" height="14" aria-hidden><Cross x={8} y={7} /></svg>{t("hist.stockout")}</span>
      </>}>
      <figure aria-label={t("hist.balances")} className="m-0">
        <figcaption className="sr-only">{t("hist.range", { n: rows.length })}</figcaption>
        <ResponsiveContainer width="100%" height={270} minWidth={0}>
          <LineChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid {...GRID} />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: AXIS.stroke }} tick={AXIS.tick} minTickGap={22} />
            <YAxis tickLine={false} axisLine={false} tick={AXIS.tick} width={46} tickFormatter={c} domain={[0, (m: number) => Math.ceil((m * 1.05) / 10000) * 10000]} />
            <ReferenceLine y={capacityCash * 0.3} stroke="var(--c-a)" strokeDasharray="2 6" opacity={0.55} />
            <Line dataKey="closing_cash" stroke="var(--c-a)" strokeWidth={2.2} dot={dot("cash")} activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
            <Line dataKey="closing_efloat" stroke="var(--c-b)" strokeWidth={2.2} strokeDasharray="7 4" dot={dot("efloat")} activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
            <Tooltip cursor={{ stroke: "var(--muted)", strokeDasharray: "4 4" }} wrapperStyle={{ outline: "none", zIndex: 20 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const r = payload[0].payload as HistoryRow;
                return (
                  <TipBox title={fmt.dateLong(r.date)}>
                    <TipRow label={t("hist.cash")} value={fmt.bdt(r.closing_cash)} color="var(--c-a)" />
                    <TipRow label={t("hist.efloat")} value={fmt.bdt(r.closing_efloat)} color="var(--c-b)" />
                    {r.cash_topup > 0 && <TipRow label={t("hist.cash_topup")} value={fmt.bdt(r.cash_topup)} />}
                    {r.efloat_topup > 0 && <TipRow label={t("hist.efloat_topup")} value={fmt.bdt(r.efloat_topup)} />}
                    {r.cash_stockout && <TipRow label={t("hist.so.cash")} value="✕" />}
                    {r.efloat_stockout && <TipRow label={t("hist.so.efloat")} value="✕" />}
                  </TipBox>
                );
              }} />
          </LineChart>
        </ResponsiveContainer>
      </figure>
    </ChartCard>
  );
}
