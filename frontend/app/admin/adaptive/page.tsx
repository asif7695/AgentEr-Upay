"use client";
import { Check, History, Settings2, Sparkles, Undo2, UserCheck, X } from "lucide-react";
import Link from "next/link";
import { ErrorState, NeuBadge, NeuButton, NeuCard, NeuSelect, NeuStat, NeuTable, Skeleton, Td, Th, Tr, cx, useToast } from "@/components/neu";
import { api, ApiError } from "@/lib/api";
import type { DictKey } from "@/lib/dict.en";
import { useI18n } from "@/lib/i18n";
import { useSim } from "@/lib/session";
import type { AdaChange, AdaMode, AdaParam, AdaReason, AdaptiveView } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const PARAMS: AdaParam[] = ["coverage_prob", "buffer_frac", "high_threshold", "watch_threshold"];
const isPct = (p: AdaParam) => p === "coverage_prob" || p === "buffer_frac";

export default function AdaptivePage() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const { bump } = useSim();
  const { data, error, reload } = useApi<AdaptiveView>("/admin/adaptive");

  if (error) return <ErrorState message={error.status === 0 ? t("common.network") : error.message} onRetry={reload} />;
  if (!data) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-24" /><Skeleton className="h-96" /></div>;

  const val = (p: AdaParam, v: number) => (isPct(p) ? fmt.pct(v * 100, 1) : fmt.pct(v, 1));
  const reasonText = (r: AdaReason) => t(`ada.reason.${r.code}` as DictKey, Object.fromEntries(Object.entries(r.params).map(([k, v]) => [k, fmt.num(v, Number.isInteger(v) ? 0 : 1)])));
  const guard = data.guard;
  const enough = data.agents.filter((a) => a.profile.n_days >= guard.min_days).length;
  const hits = data.agents.reduce((s, a) => s + a.profile.alert_hits, 0), alerts = data.agents.reduce((s, a) => s + a.profile.alert_n, 0);
  const pending = data.changes.filter((c) => c.status === "proposed");
  const history = data.changes.filter((c) => c.status !== "proposed").slice(0, 30);

  const setMode = async (mode: AdaMode) => {
    try { await api("/admin/config", { method: "PUT", body: { adaptive_mode: mode } }); toast(t("ada.mode.saved")); reload(); }
    catch (err) { toast(err instanceof ApiError ? err.message : t("common.error"), "error"); }
  };
  const decide = async (id: number, action: "approve" | "dismiss" | "revert") => {
    try { await api(`/admin/adaptive/changes/${id}/${action}`, { method: "POST" }); toast(t("ada.decided")); reload(); bump(); }
    catch (err) { toast(err instanceof ApiError ? err.message : t("common.error"), "error"); }
  };
  const changeLine = (c: AdaChange) => (Object.keys(c.params) as AdaParam[]).map((p) => {
    const v = c.params[p]!;
    return <span key={p} className="neu-inset-sm inline-flex px-2 py-0.5 text-xs font-bold">{t("ada.from_to", { param: t(`ada.param.${p}` as DictKey), from: val(p, v.from), to: val(p, v.to) })}</span>;
  });
  const settingsOf = (o: Partial<Record<AdaParam, number>>) => {
    const ks = PARAMS.filter((p) => o[p] !== undefined);
    return ks.length ? ks.map((p) => <div key={p} className="whitespace-nowrap text-xs">{t(`ada.param.${p}` as DictKey)}: <b className="tabular">{val(p, o[p]!)}</b></div>) : <span className="text-xs text-muted">{t("ada.standard")}</span>;
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold">{t("ada.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted">{t("ada.sub")}</p>
        </div>
        <NeuSelect label={t("ada.mode")} value={data.mode} onChange={(e) => setMode(e.target.value as AdaMode)} className="w-full max-w-sm">
          {(["off", "suggest", "auto"] as const).map((m) => <option key={m} value={m}>{t(`ada.mode.${m}` as DictKey)}</option>)}
        </NeuSelect>
      </div>

      <section aria-label="KPIs" className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <NeuStat label={t("ada.kpi.pending")} value={data.pending} format={fmt.num} fill={data.pending ? "yellow" : undefined} icon={<Sparkles size={18} />} />
        <NeuStat label={t("ada.kpi.active")} value={data.active} format={fmt.num} icon={<Settings2 size={18} />} />
        <NeuStat label={t("ada.kpi.evidence")} value={enough} format={fmt.num} icon={<UserCheck size={18} />} note={`${fmt.num(enough)} / ${fmt.num(data.agents.length)}`} />
        <NeuStat label={t("ada.kpi.precision")} value={alerts ? (100 * hits) / alerts : 0} format={(n) => fmt.pct(n, 0)} icon={<History size={18} />} note={t("ada.kpi.precision.note", { hits: fmt.num(hits), alerts: fmt.num(alerts) })} />
      </section>

      <NeuCard className="flex flex-col gap-3">
        <h2 className="text-base font-bold">{t("ada.pending.title")}</h2>
        {pending.length === 0 ? <p className="neu-inset p-4 text-sm text-muted">{t("ada.pending.none")}</p> : (
          <ul className="flex flex-col gap-3">
            {pending.map((c) => (
              <li key={c.id} className="neu-flat flex flex-col gap-2 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/admin/agents/${c.agent_id}`} className="font-extrabold text-accent hover:underline">{c.agent_id}</Link>
                    <span className="text-xs text-muted">{fmt.dateTiny(c.created_date)}</span>
                    {changeLine(c)}
                  </div>
                  <div className="flex gap-2">
                    <NeuButton variant="primary" onClick={() => decide(c.id, "approve")} icon={<Check size={16} aria-hidden />}>{t("ada.approve")}</NeuButton>
                    <NeuButton onClick={() => decide(c.id, "dismiss")} icon={<X size={16} aria-hidden />}>{t("ada.dismiss")}</NeuButton>
                  </div>
                </div>
                <ul className="flex flex-col gap-1 text-sm text-muted">{c.reasons.map((r, i) => <li key={i}>{reasonText(r)}</li>)}</ul>
              </li>
            ))}
          </ul>
        )}
      </NeuCard>

      <NeuCard className="flex flex-col gap-3">
        <div><h2 className="text-base font-bold">{t("ada.profiles.title")}</h2><p className="text-xs text-muted">{t("ada.profiles.sub")}</p></div>
        <NeuTable caption={t("ada.profiles.title")}>
          <thead><tr><Th>{t("ada.col.agent")}</Th><Th>{t("ada.col.breach")}</Th><Th>{t("ada.col.vol")}</Th><Th>{t("ada.col.precision")}</Th><Th>{t("ada.col.trend")}</Th><Th>{t("ada.col.reports")}</Th><Th>{t("ada.col.settings")}</Th><Th>{t("ada.col.supports")}</Th></tr></thead>
          <tbody>
            {data.agents.map((a) => {
              const p = a.profile, ok = p.n_days >= guard.min_days;
              return (
                <Tr key={a.agent_id}>
                  <Td><Link href={`/admin/agents/${a.agent_id}`} className="font-extrabold text-accent hover:underline">{a.agent_id}</Link><div className="text-xs text-muted">{t(`tier.${a.tier}` as DictKey)}</div></Td>
                  <Td className="tabular">{ok && p.breach_rate !== null ? <>{fmt.pct(100 * p.breach_rate, 0)}<div className="text-xs text-muted">{fmt.num(p.breaches)} / {fmt.num(p.n_obs)} · z {fmt.num(p.z ?? 0, 1)}</div></> : <span className="text-xs text-muted">{t("ada.nodata")}</span>}</Td>
                  <Td className="tabular">{p.vol !== null ? fmt.num(p.vol, 2) : "–"}</Td>
                  <Td className="tabular">{p.precision !== null ? <>{fmt.pct(100 * p.precision, 0)}<div className="text-xs text-muted">{fmt.num(p.alert_hits)} / {fmt.num(p.alert_n)}</div></> : "–"}</Td>
                  <Td className={cx("tabular", (p.trend_pct ?? 0) > 10 ? "text-watch" : "")}>{p.trend_pct !== null ? fmt.signed(Math.round(p.trend_pct)) + "%" : "–"}</Td>
                  <Td className="tabular">{p.report_reliability !== null ? fmt.pct(100 * p.report_reliability, 0) : "–"}</Td>
                  <Td>{settingsOf(a.active)}</Td>
                  <Td>{Object.keys(a.evidence_supports).length ? settingsOf(a.evidence_supports) : <span className="text-xs text-muted">{t("ada.no_change")}</span>}</Td>
                </Tr>
              );
            })}
          </tbody>
        </NeuTable>
      </NeuCard>

      <NeuCard className="flex flex-col gap-3">
        <h2 className="text-base font-bold">{t("ada.history.title")}</h2>
        {history.length === 0 ? <p className="neu-inset p-4 text-sm text-muted">{t("ada.history.none")}</p> : (
          <ul className="flex flex-col gap-2">
            {history.map((c) => (
              <li key={c.id} className="neu-flat flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <NeuBadge tone={c.status === "applied" ? "ok" : c.status === "reverted" ? "watch" : "neutral"}>{t(`ada.status.${c.status}` as DictKey)}</NeuBadge>
                  <Link href={`/admin/agents/${c.agent_id}`} className="font-extrabold text-accent hover:underline">{c.agent_id}</Link>
                  <span className="text-xs text-muted">{fmt.dateTiny(c.created_date)}{c.decided_by ? ` · ${c.decided_by === "system" ? t("ada.by_system") : c.decided_by}` : ""}</span>
                  {changeLine(c)}
                </div>
                {c.status === "applied" && <NeuButton onClick={() => decide(c.id, "revert")} icon={<Undo2 size={16} aria-hidden />}>{t("ada.revert")}</NeuButton>}
              </li>
            ))}
          </ul>
        )}
      </NeuCard>

      <p className="neu-inset p-3 text-xs text-muted"><b>{t("ada.guard.title")}.</b> {t("ada.guard.body", {
        days: fmt.num(guard.min_days), z: fmt.num(guard.z_gate, 1), up: fmt.num(guard.cov_up * 100) + "%", down: fmt.num(guard.cov_down * 100) + "%",
        bmin: fmt.num(guard.buf_floor * 100), bmax: fmt.num(guard.buf_cap * 100), shift: fmt.num(guard.thr_shift), gap: fmt.num(guard.min_gap), alerts: fmt.num(guard.min_alerts), cool: fmt.num(guard.cooldown_days) })}</p>
      <p className="text-xs text-muted">{data.note}</p>
    </div>
  );
}
