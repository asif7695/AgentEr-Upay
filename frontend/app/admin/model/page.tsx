"use client";
import { FlaskConical } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, GRID } from "@/components/charts/common";
import { ErrorState, NeuBadge, NeuCard, NeuTable, Skeleton, Td, Th, Tr, cx } from "@/components/neu";
import type { DictKey } from "@/lib/dict.en";
import { useI18n } from "@/lib/i18n";
import type { FamilyMetrics, ModelEvidence } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const FAMILY_ORDER = ["lightgbm_ours_cqr", "lightgbm_ours", "lognormal_gbm", "linear_quantile_regression", "seasonal_profile", "same_weekday_last_week", "supplied_bundle"];
const PATH_ORDER = ["t_copula_nu6", "t_copula_nu4", "t_copula_nu10", "correlated", "ar1", "independent"];

export default function ModelEvidencePage() {
  const { t, fmt } = useI18n();
  const { data, error, reload } = useApi<ModelEvidence>("/admin/model-evidence", { live: false });
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-24" /><Skeleton className="h-96" /></div>;

  const p = (x: number) => fmt.pct(x * 100, 1);
  const point = (m: FamilyMetrics) => m.co.coverage80 === 0 && m.ci.coverage80 === 0;      // the baseline has no interval
  const fam = (k: string) => t(`model.fam.${k}` as DictKey);
  const calRows = [
    { name: t("model.cal.before"), co: data.families.lightgbm_ours.co.coverage80 * 100, ci: data.families.lightgbm_ours.ci.coverage80 * 100 },
    { name: t("model.cal.after"), co: data.families.lightgbm_ours_cqr.co.coverage80 * 100, ci: data.families.lightgbm_ours_cqr.ci.coverage80 * 100 },
  ];
  const unseen: [string, FamilyMetrics | undefined][] = [
    ["model.unseen.agent_seen", data.unseen_agents.lightgbm_ours_agent_seen], ["model.unseen.lightgbm_ours", data.unseen_agents.lightgbm_ours],
    ["model.unseen.lightgbm_ours_cqr", data.unseen_agents.lightgbm_ours_cqr], ["model.unseen.lognormal_gbm", data.unseen_agents.lognormal_gbm],
    ["model.unseen.seasonal_profile", data.unseen_agents.seasonal_profile], ["model.unseen.same_weekday_last_week", data.unseen_agents.same_weekday_last_week],
  ];
  const events = ["adha_held_out", "adha_seen_in_training", "seasonal_profile_adha_held_out", "same_weekday_last_week"].map((k) => [`model.event.${k}`, data.unseen_event[k]] as [string, FamilyMetrics | undefined]);
  const pathRes = data.paths?.results;
  const bestTail = pathRes ? Math.min(...PATH_ORDER.map((k) => pathRes[k]["7d"].tail_error)) : 0;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-extrabold">{t("model.title")}</h1>
        <NeuBadge tone="watch" icon={<FlaskConical size={13} aria-hidden />}>{t("model.stamp")}</NeuBadge>
      </div>
      <p className="-mt-3 max-w-3xl text-sm text-muted">{t("model.sub")}</p>
      <p className="text-sm font-semibold">
        {t("model.active.now", { model: t(`model.choice.${data.active.model_choice}` as DictKey), dep: t(`dep.mode.${data.active.dependence_mode}` as DictKey) })}
      </p>

      <NeuCard className="flex flex-col gap-3">
        <div><h2 className="text-base font-bold">{t("model.compare.title")}</h2><p className="text-xs text-muted">{t("model.compare.sub")}</p></div>
        <NeuTable caption={t("model.compare.title")}>
          <thead><tr><Th>{t("model.col.model")}</Th><Th>{t("model.col.wape_co")}</Th><Th>{t("model.col.wape_ci")}</Th><Th>{t("model.col.cov_co")}</Th><Th>{t("model.col.cov_ci")}</Th><Th>{t("model.col.pinball")}</Th><Th>{t("model.col.width")}</Th></tr></thead>
          <tbody>
            {FAMILY_ORDER.filter((k) => data.families[k]).map((k) => {
              const m = data.families[k];
              const nointerval = point(m);
              return (
                <Tr key={k} className={cx(k === "lightgbm_ours_cqr" && "font-bold")}>
                  <Td>
                    {fam(k)}
                    {k === "supplied_bundle" && <span className="ml-2 text-xs font-normal text-muted">({t("model.tag.insample")})</span>}
                    {k === "lightgbm_ours_cqr" && <NeuBadge tone="accent" className="ml-2">{t("model.tag.deployed")}</NeuBadge>}
                  </Td>
                  <Td className="tabular">{fmt.num(m.co.wape, 3)}</Td><Td className="tabular">{fmt.num(m.ci.wape, 3)}</Td>
                  <Td className="tabular">{nointerval ? "–" : p(m.co.coverage80)}</Td><Td className="tabular">{nointerval ? "–" : p(m.ci.coverage80)}</Td>
                  <Td className="tabular">{nointerval ? "–" : fmt.num(m.co.pinball, 4)}</Td><Td className="tabular">{nointerval ? "–" : fmt.num(m.co.width80, 2)}</Td>
                </Tr>
              );
            })}
          </tbody>
        </NeuTable>
        <p className="text-xs text-muted">{t("model.method.2")}</p>
      </NeuCard>

      <NeuCard className="flex flex-col gap-3">
        <div><h2 className="text-base font-bold">{t("model.cal.title")}</h2><p className="text-xs text-muted">{t("model.cal.sub")}</p></div>
        <div className="neu-inset p-2 pt-4" role="img" aria-label={t("model.cal.title")} style={{ height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={calRows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="name" {...AXIS} tickLine={false} />
              <YAxis domain={[60, 90]} {...AXIS} tickLine={false} axisLine={false} unit="%" width={44} />
              <Tooltip formatter={(v: unknown) => `${fmt.num(Number(v), 1)}%`} cursor={{ fill: "var(--closed)" }} />
              <Legend />
              <ReferenceLine y={80} stroke="var(--text)" strokeDasharray="5 4" label={{ value: "80%", fill: "var(--muted)", fontSize: 12, position: "right" }} />
              <Bar dataKey="co" name={t("model.col.cov_co")} fill="var(--c-a)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="ci" name={t("model.col.cov_ci")} fill="var(--c-b)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="text-xs text-muted">{t("model.cal.note")}</p>
      </NeuCard>

      <div className="grid grid-cols-1 gap-5 2xl:grid-cols-2">
        <NeuCard className="flex flex-col gap-3">
          <div><h2 className="text-base font-bold">{t("model.unseen.title")}</h2><p className="text-xs text-muted">{t("model.unseen.sub")}</p></div>
          <NeuTable caption={t("model.unseen.title")}>
            <thead><tr><Th>{t("model.col.model")}</Th><Th>{t("model.col.wape_co")}</Th><Th>{t("model.col.wape_ci")}</Th><Th>{t("model.col.cov_co")}</Th></tr></thead>
            <tbody>
              {unseen.filter(([, m]) => m).map(([k, m]) => (
                <Tr key={k}><Td>{t(k as DictKey)}</Td><Td className="tabular">{fmt.num(m!.co.wape, 3)}</Td><Td className="tabular">{fmt.num(m!.ci.wape, 3)}</Td><Td className="tabular">{point(m!) ? "–" : p(m!.co.coverage80)}</Td></Tr>
              ))}
            </tbody>
          </NeuTable>
        </NeuCard>
        <NeuCard className="flex flex-col gap-3">
          <div><h2 className="text-base font-bold">{t("model.event.title")}</h2><p className="text-xs text-muted">{t("model.event.sub")}</p></div>
          <NeuTable caption={t("model.event.title")}>
            <thead><tr><Th>{t("model.col.model")}</Th><Th>{t("model.col.wape_co")}</Th><Th>{t("model.col.wape_ci")}</Th></tr></thead>
            <tbody>
              {events.filter(([, m]) => m).map(([k, m]) => (
                <Tr key={k}><Td>{t(k as DictKey)}</Td><Td className="tabular">{fmt.num(m!.co.wape, 3)}</Td><Td className="tabular">{fmt.num(m!.ci.wape, 3)}</Td></Tr>
              ))}
            </tbody>
          </NeuTable>
          <p className="text-xs text-muted">{t("model.event.note")}</p>
        </NeuCard>
      </div>

      {pathRes && data.paths && (
        <NeuCard className="flex flex-col gap-3">
          <div><h2 className="text-base font-bold">{t("model.path.title")}</h2><p className="text-xs text-muted">{t("model.path.sub")}</p></div>
          <NeuTable caption={t("model.path.title")}>
            <thead><tr><Th>{t("model.col.model")}</Th><Th>{t("model.path.col.3d")}</Th><Th>{t("model.path.col.7d")}</Th><Th>{t("model.path.col.cov")}</Th></tr></thead>
            <tbody>
              {PATH_ORDER.filter((k) => pathRes[k]).map((k) => (
                <Tr key={k} className={cx(pathRes[k]["7d"].tail_error === bestTail && "font-bold")}>
                  <Td>{t(`model.path.m.${k}` as DictKey)}</Td>
                  <Td className="tabular">{p(pathRes[k]["3d"].tail_error)}</Td><Td className="tabular">{p(pathRes[k]["7d"].tail_error)}</Td><Td className="tabular">{p(pathRes[k]["7d"].coverage_error)}</Td>
                </Tr>
              ))}
            </tbody>
          </NeuTable>
          <p className="text-xs text-muted">{t("model.path.est", { n: data.paths.estimate.n_origins, a: fmt.num(data.paths.estimate.rho_day, 2), b: fmt.num(data.paths.estimate.rho_cross, 2) })}</p>
        </NeuCard>
      )}

      <NeuCard className="flex flex-col gap-2">
        <h2 className="text-base font-bold">{t("model.method.title")}</h2>
        <ul className="list-disc pl-5 text-sm text-muted">
          {([0, 1, 2, 3] as const).map((i) => <li key={i}>{t(`model.method.${i}` as DictKey)}</li>)}
        </ul>
      </NeuCard>
    </div>
  );
}
