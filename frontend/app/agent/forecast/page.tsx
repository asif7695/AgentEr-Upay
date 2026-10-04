"use client";
import { ErrorState, Skeleton } from "@/components/neu";
import { ForecastView } from "@/components/forecast/ForecastView";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/session";
import type { Forecast } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function AgentForecast() {
  const { t, fmt } = useI18n();
  const { user } = useAuth();
  const { data: fc, error, reload } = useApi<Forecast>(user?.agent_id ? `/agents/${user.agent_id}/forecast` : null);
  if (error) return <ErrorState message={error.status === 0 ? t("common.network") : error.message} onRetry={reload} />;
  if (!fc) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-24" /><Skeleton className="h-72" /><Skeleton className="h-72" /></div>;
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-extrabold">{t("fc.title")}</h1>
        <p className="text-sm text-muted">{t("fc.for", { date: fmt.dateLong(fc.as_of) })}</p>
      </div>
      <ForecastView fc={fc} />
    </div>
  );
}
