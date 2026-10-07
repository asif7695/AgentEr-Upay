"use client";
import { Banknote, ClipboardList, Eye, Landmark, TriangleAlert, TrendingDown } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ReconBadge } from "@/components/forecast/parts";
import { EmptyState, ErrorState, NeuBadge, NeuButton, NeuCard, NeuSelect, NeuStat, NeuTable, Skeleton, StatusBadge, Td, Th, Tr, cx } from "@/components/neu";
import { useI18n } from "@/lib/i18n";
import type { AgentRow, Overview, Status } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function RiskCell({ pct, status }: { pct: number; status: Status }) {
  const { fmt } = useI18n();
  return <StatusBadge status={status} size="sm" label={fmt.pct(pct)} />;
}

export default function AdminOverview() {
  const { t, fmt, typeLabel } = useI18n();
  const router = useRouter();
  const { data, error, reload } = useApi<Overview>("/admin/overview");
  const [division, setDivision] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");

  const types = useMemo(() => Array.from(new Set((data?.agents ?? []).map((a) => a.location_type))).sort(), [data]);
  const rows = useMemo(() => (data?.agents ?? []).filter((a) => (!division || a.division === division) && (!type || a.location_type === type) && (!status || a.status === status)), [data, division, type, status]);

  if (error) return <ErrorState message={error.status === 0 ? t("common.network") : error.message} onRetry={reload} />;
  if (!data) return <div className="flex flex-col gap-5" aria-busy="true"><div className="grid grid-cols-2 gap-4 xl:grid-cols-6">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-32" />)}</div><Skeleton className="h-48" /><Skeleton className="h-96" /></div>;
  const k = data.kpis;
  const filtered = division || type || status;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-extrabold">{t("adm.overview.title")}</h1>
        <p className="text-sm text-muted">{t("adm.overview.sub")} · {fmt.dateLong(data.date)}</p>
      </div>

      <section aria-label="KPIs" className="grid grid-cols-2 gap-4 lg:grid-cols-3 2xl:grid-cols-6">
        <NeuStat label={t("kpi.high")} value={k.high} format={fmt.num} fill="blue" icon={<TriangleAlert size={18} />} note={`≥ ${fmt.num(data.thresholds.high)}%`} />
        <NeuStat label={t("kpi.watch")} value={k.watch} format={fmt.num} tone={k.watch ? "watch" : "ink"} icon={<Eye size={18} />} note={`${fmt.num(data.thresholds.watch)}–${fmt.num(data.thresholds.high)}%`} />
        <NeuStat label={t("kpi.unserved")} value={k.expected_unserved} format={fmt.bdt} icon={<TrendingDown size={18} />} note={t("kpi.unserved.note")} />
        <NeuStat label={t("kpi.topup")} value={k.planned_topup_total} format={fmt.bdt} icon={<Banknote size={18} />} note={t("kpi.topup.note", { c: fmt.bdt(k.planned_topup_cash), e: fmt.bdt(k.planned_topup_efloat) })} fill="yellow" />
        <NeuStat label={t("kpi.capital")} value={k.agents_needing_capital} format={fmt.num} tone={k.agents_needing_capital ? "watch" : "ink"} icon={<Landmark size={18} />} note={t("kpi.capital.note")} />
        <NeuStat label={t("kpi.reports")} value={k.reports_missing + k.reports_flagged} format={fmt.num} icon={<ClipboardList size={18} />} note={t("kpi.reports.note", { m: k.reports_missing, f: k.reports_flagged })} />
      </section>

      <section aria-label={t("div.title")}>
        <h2 className="mb-3 text-base font-bold">{t("div.title")}</h2>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {data.divisions.map((d) => {
            const active = division === d.division;
            return (
              <button key={d.division} onClick={() => setDivision(active ? "" : d.division)} aria-pressed={active}
                className={cx("flex min-h-28 flex-col gap-2 p-4 text-left transition-all duration-200", active ? "neu-inset !border-[var(--accent)]" : "neu-raised-sm hover:border-[var(--muted)]")}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold">{d.division}</span>
                  <StatusBadge status={d.worst} size="sm" />
                </div>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  {d.high > 0 && <NeuBadge tone="high" icon={<TriangleAlert size={12} aria-hidden />}>{d.high}</NeuBadge>}
                  {d.watch > 0 && <NeuBadge tone="watch" icon={<Eye size={12} aria-hidden />}>{d.watch}</NeuBadge>}
                  <NeuBadge>{t("div.agents", { n: d.agents })}</NeuBadge>
                </div>
                <span className="text-xs text-muted">{d.topup_total > 0 ? t("div.topup", { amount: fmt.num(d.topup_total) }) : t("fc.rec.none")}</span>
              </button>
            );
          })}
        </div>
      </section>

      <NeuCard className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-3">
          <NeuSelect label={t("tbl.filter.division")} value={division} onChange={(e) => setDivision(e.target.value)} className="w-44">
            <option value="">{t("common.all")}</option>
            {data.divisions.map((d) => <option key={d.division} value={d.division}>{d.division}</option>)}
          </NeuSelect>
          <NeuSelect label={t("tbl.filter.type")} value={type} onChange={(e) => setType(e.target.value)} className="w-52">
            <option value="">{t("common.all")}</option>
            {types.map((x) => <option key={x} value={x}>{typeLabel(x)}</option>)}
          </NeuSelect>
          <NeuSelect label={t("tbl.filter.status")} value={status} onChange={(e) => setStatus(e.target.value)} className="w-44">
            <option value="">{t("common.all")}</option>
            {(["HIGH", "WATCH", "OK"] as const).map((s) => <option key={s} value={s}>{t(`status.${s}` as const)}</option>)}
          </NeuSelect>
          {filtered && <NeuButton onClick={() => { setDivision(""); setType(""); setStatus(""); }}>{t("tbl.filter.reset")}</NeuButton>}
        </div>

        {rows.length === 0 ? <EmptyState message={t("tbl.none")} /> : (
          <NeuTable caption={t("adm.overview.title")}>
            <thead>
              <tr>
                <Th>{t("tbl.rank")}</Th><Th>{t("tbl.agent")}</Th><Th>{t("tbl.cash_risk")}</Th><Th>{t("tbl.ef_risk")}</Th><Th>{t("tbl.runout")}</Th>
                <Th>{t("tbl.topup")}</Th><Th>{t("tbl.report")}</Th><Th>{t("tbl.status")}</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => <AgentTr key={a.agent_id} a={a} onOpen={() => router.push(`/admin/agents/${a.agent_id}`)} />)}
            </tbody>
          </NeuTable>
        )}
        <p className="text-xs text-muted">{data.note}</p>
      </NeuCard>
    </div>
  );
}

function AgentTr({ a, onOpen }: { a: AgentRow; onOpen: () => void }) {
  const { t, fmt, typeLabel } = useI18n();
  const runout = [a.likely_cash_runout_date && `${t("tbl.cash_short")} ${fmt.date(a.likely_cash_runout_date)}`, a.likely_efloat_runout_date && `${t("tbl.ef_short")} ${fmt.date(a.likely_efloat_runout_date)}`].filter(Boolean);
  return (
    <Tr className="cursor-pointer" onClick={onOpen}>
      <Td className="tabular font-bold text-muted">{a.rank}</Td>
      <Td>
        <Link href={`/admin/agents/${a.agent_id}`} onClick={(e) => e.stopPropagation()} className="font-extrabold text-accent underline-offset-2 hover:underline">{a.agent_id}</Link>
        <div className="text-xs text-muted">{a.division} · {typeLabel(a.location_type)}</div>
        {a.has_event && <NeuBadge tone="watch" className="mt-1">{t("tbl.event")}</NeuBadge>}
      </Td>
      <Td><RiskCell pct={a.cash_risk_pct} status={a.cash_status} /><div className="mt-1 text-xs text-muted">{fmt.pct(a.cash_pct_of_capacity)} {t("common.of_capacity")}</div></Td>
      <Td><RiskCell pct={a.efloat_risk_pct} status={a.efloat_status} /><div className="mt-1 text-xs text-muted">{fmt.pct(a.efloat_pct_of_capacity)} {t("common.of_capacity")}</div></Td>
      <Td className="whitespace-nowrap text-xs" title={t("gauge.sub", { n: a.window_days })}>{runout.length ? runout.map((r, i) => <div key={i}>{r}</div>) : <span className="text-muted">{t("tbl.no_runout")}</span>}</Td>
      <Td className="whitespace-nowrap text-xs">
        {a.topup_cash > 0 && <div><b className="tabular text-sm">{fmt.bdt(a.topup_cash)}</b> {t("tbl.cash_short")}{a.topup_cash_by ? ` · ${fmt.dateTiny(a.topup_cash_by)}` : ""}</div>}
        {a.topup_efloat > 0 && <div><b className="tabular text-sm">{fmt.bdt(a.topup_efloat)}</b> {t("tbl.ef_short")}{a.topup_efloat_by ? ` · ${fmt.dateTiny(a.topup_efloat_by)}` : ""}</div>}
        {a.topup_cash <= 0 && a.topup_efloat <= 0 && <span className="text-muted">–</span>}
        {a.float_insufficient && <NeuBadge tone="watch" className="mt-1" icon={<Landmark size={12} aria-hidden />}>{t("tbl.needs_capital")}</NeuBadge>}
      </Td>
      <Td><ReconBadge rec={{ status: a.report_status }} /></Td>
      <Td><StatusBadge status={a.status} size="sm" /></Td>
    </Tr>
  );
}
