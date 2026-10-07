"use client";
import { CalendarDays, FastForward, Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { NeuButton, NeuInput, useToast } from "@/components/neu";
import { useI18n } from "@/lib/i18n";
import { useSim } from "@/lib/session";
import { shown, toData } from "@/lib/timeshift";

/** Admin top-bar controls: simulation clock, advance 1 day, jump to date, auto-play. */
export function SimControls() {
  const { t, fmt } = useI18n();
  const { sim, busy, playing, advance, jump, togglePlay, lastPipeline } = useSim();
  const toast = useToast();
  const [target, setTarget] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (sim) setTarget(sim.date); }, [sim?.date]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!sim) return null;

  const run = async (fn: () => Promise<void>) => {
    try { await fn(); } catch (e) { toast((e as Error).message, "error"); setPlaying(); }
  };
  const setPlaying = () => { if (playing) togglePlay(); };
  const doJump = () => {
    if (!target || target < sim.min_date || target > sim.max_date) { setErr(t("sim.bad_date")); return; }
    setErr(null); run(() => jump(target));
  };

  return (
    <div className="flex flex-wrap items-end gap-3" aria-label={t("sim.clock")}>
      <div className="neu-inset flex min-h-12 items-center gap-2 px-4">
        <CalendarDays size={18} className="text-accent" aria-hidden />
        <div className="leading-tight">
          <div className="text-[10px] font-bold uppercase tracking-wide text-muted">{t("sim.clock")}</div>
          <div className="tabular text-sm font-extrabold" aria-live="polite">{fmt.dateLong(sim.date)}</div>
        </div>
      </div>
      <NeuButton variant="primary" onClick={() => run(advance)} disabled={busy || !sim.can_advance} loading={busy} icon={<FastForward size={18} aria-hidden />}>
        {sim.can_advance ? t("sim.advance") : t("sim.end")}
      </NeuButton>
      <NeuButton onClick={togglePlay} aria-pressed={playing} disabled={!sim.can_advance} icon={playing ? <Pause size={18} aria-hidden /> : <Play size={18} aria-hidden />}>
        {playing ? t("sim.pause") : t("sim.play")}
      </NeuButton>
      <div className="flex items-end gap-2">
        <NeuInput type="date" aria-label={t("sim.jump")} value={shown(target)} min={shown(sim.min_date)} max={shown(sim.max_date)} onChange={(e) => setTarget(toData(e.target.value))} error={err} className="w-44" />
        <NeuButton onClick={doJump} disabled={busy}>{t("sim.go")}</NeuButton>
      </div>
      <NeuButton onClick={() => run(() => jump("2025-09-01"))} disabled={busy} aria-label={t("sim.reset")} title={t("sim.reset")} className="!px-0"><RotateCcw size={18} aria-hidden /></NeuButton>
      {lastPipeline && (
        <p className="w-full text-xs text-muted" role="status">
          {t("sim.pipeline", { date: fmt.dateTiny(lastPipeline.date), rows: lastPipeline.ledger_rows_ingested, reports: lastPipeline.reports_requested, fc: lastPipeline.forecasts_recomputed, alerts: lastPipeline.alerts_created, ms: lastPipeline.elapsed_ms })}
        </p>
      )}
    </div>
  );
}
