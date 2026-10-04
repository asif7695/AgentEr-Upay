"use client";
import { CheckCircle2, ClipboardEdit } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ActionCard, ReconCard } from "@/components/forecast/parts";
import { ErrorState, NeuButton, NeuCard, NeuInput, Skeleton, useToast } from "@/components/neu";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { parseAmount } from "@/lib/parse";
import { useAuth, useSim } from "@/lib/session";
import type { Forecast } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function ReportPage() {
  const { t, fmt } = useI18n();
  const { user } = useAuth();
  const { sim, bump } = useSim();
  const toast = useToast();
  const aid = user?.agent_id;
  const { data: fc, error: loadErr, reload } = useApi<Forecast>(aid ? `/agents/${aid}/forecast?explain=false` : null);
  const [value, setValue] = useState("");           // intentionally empty: the form prefills nothing
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ message: string; forecast: Forecast } | null>(null);

  const validate = (raw: string): string | null => {
    if (!raw.trim()) return t("report.err.required");
    const n = parseAmount(raw);
    if (Number.isNaN(n)) return t("report.err.number");
    if (n < 0) return t("report.err.negative");
    if (n > 1_000_000_000) return t("report.err.big");
    return null;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const v = validate(value);
    setErr(v);
    if (v || !aid) return;
    setBusy(true);
    try {
      const r = await api<{ message: string; forecast: Forecast }>(`/agents/${aid}/cash-report`, { method: "POST", body: { cash: parseAmount(value) } });
      setResult(r); bump(); reload(); toast(t("report.submitted_toast"));
    } catch (e2) {
      setErr(e2 instanceof ApiError ? (e2.status === 0 ? t("common.network") : e2.message) : t("common.error"));
    } finally { setBusy(false); }
  };

  if (loadErr) return <ErrorState message={loadErr.message} onRetry={reload} />;
  if (!fc || !sim) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-56" /><Skeleton className="h-40" /></div>;
  const live = result?.forecast ?? fc;
  const gp = live.reconciliation.gap_pct;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-extrabold">{t("report.title")}</h1>
        <p className="text-sm text-muted">{t("report.for", { date: fmt.dateLong(sim.date) })}</p>
      </div>
      <NeuCard className="flex flex-col gap-4">
        <p className="text-sm">{t("report.sub")}</p>
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          <NeuInput label={t("report.label")} inputMode="decimal" autoComplete="off" placeholder={t("report.placeholder")} value={value}
            onChange={(e) => { setValue(e.target.value); if (err) setErr(validate(e.target.value)); }} error={err} />
          <NeuButton type="submit" variant="primary" loading={busy} icon={<ClipboardEdit size={18} aria-hidden />}>{t("report.submit")}</NeuButton>
        </form>
      </NeuCard>

      {result && (
        <NeuCard className="flex flex-col gap-3" role="status" aria-live="polite">
          <div className="flex items-center gap-2 font-bold"><CheckCircle2 size={20} className="text-ok" aria-hidden />{t("report.result")}</div>
          <p className="text-sm">
            {result.forecast.reconciliation.flagged
              ? t("report.flagged", { gap: gp == null ? "" : ` (${fmt.signed(gp * 100)}%)` })
              : t("report.thanks")}
          </p>
        </NeuCard>
      )}

      <ReconCard rec={live.reconciliation} />
      {result && (
        <NeuCard className="flex flex-col gap-3">
          <h2 className="text-base font-bold">{t("report.forecast_updated")}</h2>
          <p className="text-sm text-muted">{t("report.new_risk")}: <b className="tabular text-ink">{fmt.pct(live.cash.risk_pct, 1)}</b> · {t(`status.${live.cash.status}` as const)}</p>
        </NeuCard>
      )}
      <ActionCard fc={live} />
    </div>
  );
}
