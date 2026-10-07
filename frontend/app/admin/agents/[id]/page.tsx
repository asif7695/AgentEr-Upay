"use client";
import { ArrowLeft, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { AlertList } from "@/components/AlertList";
import { ForecastView } from "@/components/forecast/ForecastView";
import { ActionCard, ReconBadge, ReconCard } from "@/components/forecast/parts";
import { EmptyState, ErrorState, NeuBadge, NeuCard, NeuTable, NeuToggle, Skeleton, StatusBadge, Td, Th, Tr, useToast } from "@/components/neu";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSim } from "@/lib/session";
import type { AlertItem, Forecast, History, Reveal } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function AgentDetail() {
  const params = useParams<{ id: string }>();
  const id = String(params.id).toUpperCase();
  const { t, fmt, typeLabel } = useI18n();
  const { sim } = useSim();
  const toast = useToast();
  const [reveal, setReveal] = useState(false);
  const { data: fc, error, reload } = useApi<Forecast>(`/agents/${id}/forecast`);
  const { data: hist } = useApi<History>(`/agents/${id}/history?days=30`);
  const { data: alerts, reload: reloadAlerts } = useApi<AlertItem[]>(`/alerts?agent_id=${id}&limit=20`);
  const { data: rv, error: rvErr } = useApi<Reveal>(reveal && sim?.can_reveal ? `/agents/${id}/reveal` : null);

  if (error) return <div className="flex flex-col gap-4"><BackLink /><ErrorState message={error.status === 0 ? t("common.network") : error.message} onRetry={reload} /></div>;
  if (!fc) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-16" /><Skeleton className="h-72" /><Skeleton className="h-72" /></div>;

  const ack = async (aid: number) => { try { await api(`/alerts/${aid}/ack`, { method: "POST" }); reloadAlerts(); } catch (e) { toast((e as Error).message, "error"); } };
  const revealOn = reveal && !!rv;

  return (
    <div className="flex flex-col gap-5">
      <BackLink />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-extrabold">{t("adm.agent.title")}: {id}</h1>
            <StatusBadge status={fc.status} />
            <ReconBadge rec={fc.reconciliation} />
          </div>
          <p className="text-sm text-muted">{fc.agent.division} · {typeLabel(fc.agent.location_type)} · {t("term.capacity")}: {t("term.cash")} {fmt.bdt(fc.agent.capacity_cash)}, {t("term.efloat")} {fmt.bdt(fc.agent.capacity_efloat)}</p>
        </div>
        <NeuCard variant="inset" className="flex max-w-sm flex-col gap-1 !p-3">
          <NeuToggle checked={reveal} onChange={setReveal} label={t("adm.agent.reveal")} />
          <p className="text-xs text-muted">{sim?.can_reveal ? t("adm.agent.reveal.sub") : t("adm.agent.reveal.unavailable", { date: fmt.date(sim?.reveal_max_date ?? "2025-12-24") })}</p>
        </NeuCard>
      </div>

      {reveal && sim?.can_reveal && (
        <section aria-live="polite" className="flex flex-col gap-3">
          <p role="note" className="flex items-center gap-2 rounded-2xl px-4 py-3 text-sm font-bold" style={{ background: "var(--accent-2)", color: "var(--brand-ink)" }}>
            <Sparkles size={18} aria-hidden />{t("reveal.banner")}
          </p>
          {rvErr && <ErrorState message={rvErr.message} />}
          {rv && <RevealSummary rv={rv} />}
        </section>
      )}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="xl:col-span-2"><ActionCard fc={fc} /></div>
        <ReconCard rec={fc.reconciliation} tolerance={10} />
      </div>

      <ForecastView fc={fc} reveal={revealOn ? rv : null} />

      <NeuCard className="flex flex-col gap-3">
        <h2 className="text-base font-bold">{t("adm.agent.recon")}</h2>
        {!hist ? <Skeleton className="h-40" /> : (
          <div className="max-h-96 overflow-y-auto neu-scroll">
            <NeuTable caption={t("adm.agent.recon")}>
              <thead><tr><Th>{t("fc.col.date")}</Th><Th>{t("rec.ledger")}</Th><Th>{t("rec.reported")}</Th><Th>{t("rec.gap")}</Th><Th>{t("common.status")}</Th></tr></thead>
              <tbody>
                {[...hist.rows].reverse().map((r) => (
                  <Tr key={r.date}>
                    <Td className="whitespace-nowrap font-semibold">{fmt.date(r.date)}</Td>
                    <Td className="tabular">{fmt.bdt(r.closing_cash)}</Td>
                    <Td className="tabular">{r.report.reported_cash == null ? "–" : fmt.bdt(r.report.reported_cash)}</Td>
                    <Td className="tabular">{r.report.gap == null ? "–" : `${fmt.signed(r.report.gap)}${r.report.gap_pct == null ? "" : ` (${fmt.signed(r.report.gap_pct * 100)}%)`}`}</Td>
                    <Td><ReconBadge rec={r.report} /></Td>
                  </Tr>
                ))}
              </tbody>
            </NeuTable>
          </div>
        )}
      </NeuCard>

      <NeuCard className="flex flex-col gap-3">
        <h2 className="text-base font-bold">{t("adm.agent.alerts")}</h2>
        {!alerts ? <Skeleton className="h-24" /> : alerts.length === 0 ? <EmptyState message={t("alerts.none")} /> : <AlertList alerts={alerts} onAck={ack} showAgent={false} />}
      </NeuCard>
    </div>
  );
}

function BackLink() {
  const { t } = useI18n();
  return <Link href="/admin" className="inline-flex min-h-11 w-fit items-center gap-2 text-sm font-bold text-accent"><ArrowLeft size={16} aria-hidden />{t("adm.agent.back")}</Link>;
}

function RevealSummary({ rv }: { rv: Reveal }) {
  const { t, fmt } = useI18n();
  const s = rv.summary;
  return (
    <NeuCard className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-bold">{t("reveal.outcome")}</h3>
        <NeuBadge tone={s.cash_stockout_days + s.efloat_stockout_days > 0 ? "high" : "ok"}>{t("reveal.stockouts", { c: s.cash_stockout_days, e: s.efloat_stockout_days })}</NeuBadge>
        <NeuBadge>{t("reveal.unserved", { amount: fmt.num(s.unserved_total) })}</NeuBadge>
      </div>
      <p className="text-sm text-muted">
        {t("reveal.counterfactual")}: {t("term.cash")} — {s.counterfactual_cash_breach ? t("reveal.breach.yes") : t("reveal.breach.no")}; {t("term.efloat")} — {s.counterfactual_efloat_breach ? t("reveal.breach.yes") : t("reveal.breach.no")}.
      </p>
      <NeuTable caption={t("reveal.outcome")}>
        <thead>
          <tr><Th>{t("fc.col.date")}</Th><Th>{t("term.cashout")} · {t("reveal.col.true")}</Th><Th>{t("term.cashout")} · {t("reveal.col.served")}</Th><Th>{t("term.cashin")} · {t("reveal.col.true")}</Th><Th>{t("term.cashin")} · {t("reveal.col.served")}</Th><Th>{t("hist.col.cash")}</Th><Th>{t("hist.col.efloat")}</Th><Th>{t("hist.col.flags")}</Th></tr>
        </thead>
        <tbody>
          {rv.days.map((d) => (
            <Tr key={d.date}>
              <Td className="whitespace-nowrap font-semibold">{fmt.date(d.date)}</Td>
              <Td className="tabular">{fmt.bdt(d.true_cashout)}</Td><Td className="tabular">{fmt.bdt(d.served_cashout)}</Td>
              <Td className="tabular">{fmt.bdt(d.true_cashin)}</Td><Td className="tabular">{fmt.bdt(d.served_cashin)}</Td>
              <Td className="tabular">{fmt.bdt(d.closing_cash)}</Td><Td className="tabular">{fmt.bdt(d.closing_efloat)}</Td>
              <Td>{d.cash_stockout && <NeuBadge tone="high">{t("hist.so.cash")}</NeuBadge>} {d.efloat_stockout && <NeuBadge tone="high">{t("hist.so.efloat")}</NeuBadge>}{!d.cash_stockout && !d.efloat_stockout && <span className="text-muted">–</span>}</Td>
            </Tr>
          ))}
        </tbody>
      </NeuTable>
    </NeuCard>
  );
}
