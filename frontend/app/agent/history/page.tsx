"use client";
import { CircleCheck, XCircle } from "lucide-react";
import { useState } from "react";
import { HistoryChart } from "@/components/charts/HistoryChart";
import { ReconBadge } from "@/components/forecast/parts";
import { ErrorState, NeuBadge, NeuCard, NeuSelect, NeuStat, NeuTable, Skeleton, Td, Th, Tr } from "@/components/neu";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/session";
import type { History } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function HistoryPage() {
  const { t, fmt } = useI18n();
  const { user } = useAuth();
  const [days, setDays] = useState(60);
  const { data, error, reload } = useApi<History>(user?.agent_id ? `/agents/${user.agent_id}/history?days=${days}` : null);
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-24" /><Skeleton className="h-72" /><Skeleton className="h-64" /></div>;
  const rows = [...data.rows].reverse();
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-extrabold">{t("hist.title")}</h1><p className="text-sm text-muted">{t("hist.range", { n: data.rows.length })}</p></div>
        <NeuSelect aria-label={t("hist.range", { n: days })} value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-44">
          {[30, 60, 120, 365].map((n) => <option key={n} value={n}>{t("hist.range", { n })}</option>)}
        </NeuSelect>
      </div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <NeuStat label={`${t("hist.stockout_days")} · ${t("term.cash")}`} value={data.totals.cash_stockout_days} format={fmt.num} tone={data.totals.cash_stockout_days ? "high" : "ink"} />
        <NeuStat label={`${t("hist.stockout_days")} · ${t("term.efloat")}`} value={data.totals.efloat_stockout_days} format={fmt.num} tone={data.totals.efloat_stockout_days ? "high" : "ink"} />
        <NeuStat label={`${t("hist.topups")} · ${t("term.cash")}`} value={data.totals.cash_topups} format={fmt.num} />
        <NeuStat label={`${t("hist.topups")} · ${t("term.efloat")}`} value={data.totals.efloat_topups} format={fmt.num} />
      </div>
      <HistoryChart rows={data.rows} capacityCash={data.capacity_cash} />
      <NeuCard className="flex flex-col gap-3">
        <h2 className="text-base font-bold">{t("hist.table")}</h2>
        <div className="max-h-[28rem] overflow-y-auto neu-scroll">
          <NeuTable caption={t("hist.table")}>
            <thead><tr><Th>{t("fc.col.date")}</Th><Th>{t("hist.col.cash")}</Th><Th>{t("hist.col.efloat")}</Th><Th>{t("hist.col.topup")}</Th><Th>{t("hist.col.flags")}</Th><Th>{t("hist.col.report")}</Th></tr></thead>
            <tbody>
              {rows.slice(0, 120).map((r) => (
                <Tr key={r.date}>
                  <Td className="whitespace-nowrap font-semibold">{fmt.date(r.date)}</Td>
                  <Td className="tabular">{fmt.bdt(r.closing_cash)}</Td>
                  <Td className="tabular">{fmt.bdt(r.closing_efloat)}</Td>
                  <Td className="tabular text-xs">
                    {r.cash_topup > 0 && <div>{t("hist.cash_topup")}: {fmt.bdt(r.cash_topup)}</div>}
                    {r.efloat_topup > 0 && <div>{t("hist.efloat_topup")}: {fmt.bdt(r.efloat_topup)}</div>}
                    {r.cash_topup <= 0 && r.efloat_topup <= 0 && <span className="text-muted">–</span>}
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1.5">
                      {r.cash_stockout && <NeuBadge tone="high" icon={<XCircle size={13} aria-hidden />}>{t("hist.so.cash")}</NeuBadge>}
                      {r.efloat_stockout && <NeuBadge tone="high" icon={<XCircle size={13} aria-hidden />}>{t("hist.so.efloat")}</NeuBadge>}
                      {!r.cash_stockout && !r.efloat_stockout && <span className="inline-flex items-center gap-1 text-xs text-muted"><CircleCheck size={13} aria-hidden />{t("hist.none")}</span>}
                    </div>
                  </Td>
                  <Td><ReconBadge rec={r.report} /></Td>
                </Tr>
              ))}
            </tbody>
          </NeuTable>
        </div>
      </NeuCard>
    </div>
  );
}
