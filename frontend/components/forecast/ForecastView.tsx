"use client";
import { BalanceChart } from "@/components/charts/BalanceChart";
import { FanChart } from "@/components/charts/FanChart";
import { RiskCurve } from "@/components/charts/RiskCurve";
import { NeuCard } from "@/components/neu";
import { useI18n } from "@/lib/i18n";
import type { Forecast, Reveal } from "@/lib/types";
import { DayTable, EventBanner, RecommendPanel, RiskPanel, WhyPanel } from "./parts";

/** The full forecast view, shared by the agent app and the admin agent-detail page. */
export function ForecastView({ fc, reveal }: { fc: Forecast; reveal?: Reveal | null }) {
  const { t, fmt } = useI18n();
  const rv = reveal?.days ?? null;
  return (
    <div className="flex flex-col gap-5">
      <EventBanner fc={fc} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        <div className="xl:col-span-2"><RiskPanel fc={fc} /></div>
        <div className="xl:col-span-3"><RiskCurve fc={fc} /></div>
      </div>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <FanChart days={fc.days} flow="cashout" reveal={rv} />
        <FanChart days={fc.days} flow="cashin" reveal={rv} />
      </div>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <BalanceChart kind="cash" dates={fc.bands.dates} bands={fc.bands.cash} buffer={fc.bands.buffer_cash} bufferFrac={fc.config.buffer_frac} days={fc.days} reveal={rv} />
        <BalanceChart kind="efloat" dates={fc.bands.dates} bands={fc.bands.efloat} buffer={fc.bands.buffer_efloat} bufferFrac={fc.config.buffer_frac} days={fc.days} reveal={rv} />
      </div>
      <RecommendPanel fc={fc} />
      <DayTable fc={fc} />
      <WhyPanel fc={fc} />
      <NeuCard variant="flat" className="text-xs text-muted">
        {t("fc.source")} · {t("fc.for", { date: fmt.dateLong(fc.as_of) })}
      </NeuCard>
    </div>
  );
}
