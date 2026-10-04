"use client";
import { Banknote, Smartphone } from "lucide-react";
import { useRouter } from "next/navigation";
import { AlertList } from "@/components/AlertList";
import { ActionCard, ReconCard, RiskPanel } from "@/components/forecast/parts";
import { ErrorState, NeuCard, NeuStat, Skeleton, useToast } from "@/components/neu";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth, useSim } from "@/lib/session";
import type { AlertItem, Forecast } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function AgentHome() {
  const { t, fmt, typeLabel } = useI18n();
  const { user } = useAuth();
  const { sim } = useSim();
  const router = useRouter();
  const toast = useToast();
  const aid = user?.agent_id;
  const { data: fc, error, reload } = useApi<Forecast>(aid ? `/agents/${aid}/forecast?explain=false` : null);
  const { data: alerts, reload: reloadAlerts } = useApi<AlertItem[]>("/alerts?status=open&limit=5");

  if (error) return <ErrorState message={error.status === 0 ? t("common.network") : error.message} onRetry={reload} />;
  if (!fc || !sim) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-24" /><Skeleton className="h-80" /><Skeleton className="h-40" /></div>;

  const ack = async (id: number) => { try { await api(`/alerts/${id}/ack`, { method: "POST" }); reloadAlerts(); } catch (e) { toast((e as Error).message, "error"); } };

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-extrabold">{t("home.hello", { name: user?.display_name ?? "" })}</h1>
        <p className="text-sm text-muted">{t("home.today")}: <b className="text-ink">{fmt.dateLong(sim.date)}</b> · {t("home.division", { division: fc.agent.division, type: typeLabel(fc.agent.location_type) })}</p>
      </div>
      <RiskPanel fc={fc} />
      <ActionCard fc={fc} onNavigate={(a) => router.push(a.type === "submit_report" || a.type === "verify_report" ? "/agent/report" : "/agent/forecast")} />
      <div className="grid grid-cols-2 gap-4">
        <NeuStat label={`${t("term.cash")} · ${t("home.balance_now")}`} value={fc.cash.current} format={fmt.bdt} icon={<Banknote size={18} />}
          note={`${t("gauge.of_cap", { pct: fmt.num(fc.cash.pct_of_capacity) })} · ${fc.balances.cash.source === "reported" ? t("rec.source.reported") : t("rec.source.ledger_estimate")}`} />
        <NeuStat label={`${t("term.efloat")} · ${t("home.balance_now")}`} value={fc.efloat.current} format={fmt.bdt} icon={<Smartphone size={18} />}
          note={t("gauge.of_cap", { pct: fmt.num(fc.efloat.pct_of_capacity) })} />
      </div>
      <ReconCard rec={fc.reconciliation} tolerance={10} compact />
      {alerts && alerts.length > 0 && (
        <NeuCard className="flex flex-col gap-3">
          <h2 className="text-base font-bold">{t("alerts.title")}</h2>
          <AlertList alerts={alerts} onAck={ack} showAgent={false} />
        </NeuCard>
      )}
    </div>
  );
}
