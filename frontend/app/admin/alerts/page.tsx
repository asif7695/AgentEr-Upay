"use client";
import { useState } from "react";
import { AlertList } from "@/components/AlertList";
import { EmptyState, ErrorState, NeuCard, NeuTabs, Skeleton, useToast } from "@/components/neu";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { AlertItem } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function AlertsPage() {
  const { t } = useI18n();
  const toast = useToast();
  const [tab, setTab] = useState<"open" | "acked">("open");
  const { data, error, reload } = useApi<AlertItem[]>(`/alerts?status=${tab}&limit=200`);
  const ack = async (id: number) => { try { await api(`/alerts/${id}/ack`, { method: "POST" }); reload(); } catch (e) { toast((e as Error).message, "error"); } };
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl font-extrabold">{t("alerts.title")}</h1>
      <NeuTabs label={t("alerts.title")} value={tab} onChange={setTab} tabs={[{ id: "open", label: t("alerts.open") }, { id: "acked", label: t("alerts.acked") }]} />
      <NeuCard>
        {error ? <ErrorState message={error.message} onRetry={reload} /> : !data ? <Skeleton className="h-48" /> : data.length === 0 ? <EmptyState message={t("alerts.none")} /> : <AlertList alerts={data} onAck={tab === "open" ? ack : undefined} />}
      </NeuCard>
    </div>
  );
}
