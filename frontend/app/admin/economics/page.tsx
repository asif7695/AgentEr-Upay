"use client";
import { CircleCheck, FlaskConical, Save, Sparkles, TriangleAlert, Undo2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, GRID } from "@/components/charts/common";
import { ErrorState, NeuBadge, NeuButton, NeuCard, NeuInput, NeuSelect, NeuTable, Skeleton, Td, Th, Tr, cx, useToast } from "@/components/neu";
import { api, ApiError } from "@/lib/api";
import type { DictKey } from "@/lib/dict.en";
import { useI18n } from "@/lib/i18n";
import { useSim } from "@/lib/session";
import type { EconomicsView, PolicyNet } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const TIERS = ["garment_urban", "market_urban", "remittance_urban", "university_urban", "rural"] as const;
const POLICIES = ["habit", "hybrid95", "optimum", "model_only95"] as const;

export default function EconomicsPage() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const { bump } = useSim();
  const { data, error, reload } = useApi<EconomicsView>("/admin/economics", { live: false });
  const [vals, setVals] = useState<Record<string, string>>({});
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [tier, setTier] = useState<(typeof TIERS)[number]>("garment_urban");

  const load = (d: EconomicsView) => {
    const a = d.assumptions;
    const v: Record<string, string> = { margin: String(+(a.margin_rate * 100).toFixed(3)), share: String(+(a.agent_share * 100).toFixed(1)), mult: String(a.customer_multiplier), capital: String(+(a.capital_cost_annual * 100).toFixed(2)) };
    for (const tr of TIERS) v[`trip_${tr}`] = String(a.trip_cost[tr]);
    setVals(v); setErrs({});
  };
  useEffect(() => { if (data) load(data); }, [data]);

  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-24" /><Skeleton className="h-96" /></div>;

  const money = (n: number) => `${n < 0 ? "−" : ""}${fmt.bdt(Math.abs(Math.round(n)))}`;
  const p1 = (x: number) => fmt.pct(x * 100, 1);
  const tl = (k: string) => t(`tier.${k}` as DictKey);
  const pol = data.policies;
  const habit = pol.habit, opt = pol.optimum, h95 = pol.hybrid95;

  const validate = () => {
    const e: Record<string, string> = {};
    const num = (k: string, lo: number, hi: number) => { const n = Number(vals[k]); if (vals[k]?.trim() === "" || !Number.isFinite(n) || n < lo || n > hi) e[k] = t("rules.bounds", { lo: fmt.num(lo, 2), hi: fmt.num(hi, 2) }); };
    for (const tr of TIERS) num(`trip_${tr}`, data.bounds.trip_cost[0], data.bounds.trip_cost[1]);
    num("margin", data.bounds.margin_rate[0] * 100, data.bounds.margin_rate[1] * 100); num("share", 0, 100);
    num("mult", data.bounds.customer_multiplier[0], data.bounds.customer_multiplier[1]); num("capital", 0, 100);
    return e;
  };
  const save = async (ev: FormEvent) => {
    ev.preventDefault();
    const e = validate(); setErrs(e);
    if (Object.keys(e).length) { toast(t("rules.invalid"), "error"); return; }
    const trip_cost: Record<string, number> = {};
    for (const tr of TIERS) trip_cost[tr] = Number(vals[`trip_${tr}`]);
    setBusy(true);
    try {
      await api("/admin/economics", { method: "PUT", body: { trip_cost, margin_rate: Number(vals.margin) / 100, agent_share: Number(vals.share) / 100, customer_multiplier: Number(vals.mult), capital_cost_annual: Number(vals.capital) / 100 } });
      toast(t("eco.assume.saved")); reload();
    } catch (err) { toast(err instanceof ApiError ? err.message : t("common.error"), "error"); } finally { setBusy(false); }
  };
  const restore = () => {
    const d = data.defaults; const v: Record<string, string> = { margin: String(+(d.margin_rate * 100).toFixed(3)), share: String(+(d.agent_share * 100).toFixed(1)), mult: String(d.customer_multiplier), capital: String(+(d.capital_cost_annual * 100).toFixed(2)) };
    for (const tr of TIERS) v[`trip_${tr}`] = String(d.trip_cost[tr]);
    setVals(v); setErrs({});
  };
  const apply = async () => {
    try { await api("/admin/economics/apply-optimum", { method: "POST" }); toast(t("eco.apply.done")); reload(); bump(); }
    catch (err) { toast(err instanceof ApiError ? err.message : t("common.error"), "error"); }
  };

  const tr = data.tiers[tier];
  const curve = tr.curve.map((c) => ({ ...c, cov: Math.round(c.coverage * 1000) / 10 }));
  const opt_pt = curve.find((c) => c.coverage === tr.optimum.coverage);
  const pt95 = curve.find((c) => c.coverage === 0.95);

  const verdictNode = data.verdict === "model_guided_pays" ? (
    <>
      <p className="text-sm font-semibold">{t("eco.verdict.pays", { saved: money(opt.net_benefit), pct: p1(opt.net_benefit / Math.max(habit.total, 1)), orders: opt.orders, habitOrders: habit.orders, so: opt.stockout_days, habitSo: habit.stockout_days })}</p>
      {opt.orders < habit.orders && <p className="text-sm text-muted">{t("eco.verdict.larger")}</p>}
      <p className="text-sm text-muted">{h95.net_benefit < 0 ? t("eco.verdict.95.loses", { amount: money(-h95.net_benefit) }) : t("eco.verdict.95.gains", { amount: money(h95.net_benefit) })}</p>
    </>
  ) : <p className="text-sm font-semibold">{t("eco.verdict.no")}</p>;

  const policyRow = (k: (typeof POLICIES)[number], v: PolicyNet) => (
    <Tr key={k} className={cx(k === "optimum" && "font-bold")}>
      <Td>{t(`eco.pol.${k}` as DictKey)}</Td>
      <Td className="tabular">{fmt.num(v.orders)}</Td><Td className="tabular">{fmt.num(v.stockout_days)}</Td><Td className="tabular">{fmt.num(Math.round(v.unserved))}</Td>
      <Td className="tabular">{p1(v.service_rate)}</Td><Td className="tabular">{fmt.num(Math.round(v.total))}</Td>
      <Td className={cx("tabular", v.net_benefit > 0 ? "text-ok" : v.net_benefit < 0 ? "text-high" : "")}>{k === "habit" ? "–" : money(v.net_benefit)}</Td>
    </Tr>
  );
  const sameApplied = (k: string) => { const a = data.applied[k], o = data.optimum_params[k]; return a.coverage === o.coverage && a.buffer === o.buffer && a.up === o.up; };
  const sensRows = [0.25, 0.5, 1, 2], sensCols = [1, 2, 5, 10, 20];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-extrabold">{t("eco.title")}</h1>
        <NeuBadge tone="watch" icon={<FlaskConical size={13} aria-hidden />}>{t("model.stamp")}</NeuBadge>
      </div>
      <p className="-mt-3 max-w-3xl text-sm text-muted">{t("eco.sub")}</p>
      <p role="note" className="neu-inset flex items-start gap-2 p-3 text-xs text-muted"><TriangleAlert size={15} className="mt-0.5 shrink-0" aria-hidden />{t("eco.banner")}</p>

      <NeuCard className="flex flex-col gap-2" role="status">{verdictNode}</NeuCard>

      <NeuCard className="flex flex-col gap-3">
        <div><h2 className="text-base font-bold">{t("eco.policy.title")}</h2><p className="text-xs text-muted">{t("eco.policy.sub")}</p></div>
        <NeuTable caption={t("eco.policy.title")}>
          <thead><tr><Th>{t("eco.col.policy")}</Th><Th>{t("eco.col.orders")}</Th><Th>{t("eco.col.so")}</Th><Th>{t("eco.col.unserved")}</Th><Th>{t("eco.col.service")}</Th><Th>{t("eco.col.cost")}</Th><Th>{t("eco.col.net")}</Th></tr></thead>
          <tbody>{POLICIES.map((k) => policyRow(k, pol[k]))}</tbody>
        </NeuTable>
      </NeuCard>

      <NeuCard>
        <form onSubmit={save} className="flex flex-col gap-4" noValidate>
          <h2 className="text-base font-bold">{t("eco.assume.title")}</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {TIERS.map((k) => (
              <NeuInput key={k} label={t("eco.assume.trip", { tier: tl(k) })} inputMode="decimal" value={vals[`trip_${k}`] ?? ""} onChange={(e) => setVals({ ...vals, [`trip_${k}`]: e.target.value })} error={errs[`trip_${k}`]} />
            ))}
            <NeuInput label={t("eco.assume.margin")} inputMode="decimal" value={vals.margin ?? ""} onChange={(e) => setVals({ ...vals, margin: e.target.value })} error={errs.margin} />
            <NeuInput label={t("eco.assume.agent_share")} inputMode="decimal" value={vals.share ?? ""} onChange={(e) => setVals({ ...vals, share: e.target.value })} error={errs.share} />
            <NeuInput label={t("eco.assume.mult")} inputMode="decimal" value={vals.mult ?? ""} onChange={(e) => setVals({ ...vals, mult: e.target.value })} error={errs.mult} />
            <NeuInput label={t("eco.assume.capital")} inputMode="decimal" value={vals.capital ?? ""} onChange={(e) => setVals({ ...vals, capital: e.target.value })} error={errs.capital} />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <NeuButton type="submit" variant="primary" loading={busy} icon={<Save size={18} aria-hidden />}>{t("eco.assume.save")}</NeuButton>
            <NeuButton onClick={restore} icon={<Undo2 size={18} aria-hidden />}>{t("eco.assume.reset")}</NeuButton>
          </div>
        </form>
      </NeuCard>

      <NeuCard className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div><h2 className="text-base font-bold">{t("eco.curve.title")}</h2><p className="text-xs text-muted">{t("eco.curve.sub")}</p></div>
          <NeuSelect label={t("eco.curve.tier")} value={tier} onChange={(e) => setTier(e.target.value as (typeof TIERS)[number])} className="w-56">
            {TIERS.map((k) => <option key={k} value={k}>{tl(k)}</option>)}
          </NeuSelect>
        </div>
        <div className="neu-inset p-2 pt-4" role="img" aria-label={t("eco.curve.title")} style={{ height: 300 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={curve} margin={{ top: 8, right: 20, left: 4, bottom: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="cov" {...AXIS} tickLine={false} unit="%" />
              <YAxis {...AXIS} tickLine={false} axisLine={false} width={64} tickFormatter={(v: number) => fmt.num(Math.round(v))} domain={["auto", "auto"]} />
              <Tooltip formatter={(v: unknown) => money(Number(v))} labelFormatter={(l) => `${l}%`} />
              <Legend />
              <Line type="monotone" dataKey="cost_default" name={t("eco.curve.default")} stroke="var(--c-a)" strokeWidth={2.5} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="cost_best" name={t("eco.curve.best")} stroke="var(--c-b)" strokeWidth={2.5} strokeDasharray="6 4" dot={{ r: 3 }} />
              {pt95 && <ReferenceDot x={pt95.cov} y={pt95.cost_default} r={7} fill="var(--surface)" stroke="var(--text)" strokeWidth={2} label={{ value: t("eco.curve.at95"), position: "top", fill: "var(--muted)", fontSize: 12 }} />}
              {opt_pt && <ReferenceDot x={opt_pt.cov} y={opt_pt.cost_best} r={7} fill="var(--c-b)" stroke="var(--text)" strokeWidth={2} label={{ value: t("eco.curve.opt"), position: "right", fill: "var(--muted)", fontSize: 12 }} />}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </NeuCard>

      <NeuCard className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-bold">{t("eco.tier.title")}</h2>
          <NeuButton variant="primary" onClick={apply} icon={<Sparkles size={18} aria-hidden />}>{t("eco.apply")}</NeuButton>
        </div>
        <p className="text-xs text-muted">{t("eco.apply.note")}</p>
        <NeuTable caption={t("eco.tier.title")}>
          <thead><tr><Th>{t("eco.col.tier")}</Th><Th>{t("eco.col.net95")}</Th><Th>{t("eco.col.cov")}</Th><Th>{t("eco.col.buf")}</Th><Th>{t("eco.col.up")}</Th><Th>{t("eco.col.netopt")}</Th><Th>{t("eco.col.be_trip")}</Th><Th>{t("eco.col.be_mult")}</Th><Th>{t("eco.col.applied")}</Th></tr></thead>
          <tbody>
            {TIERS.map((k) => {
              const v = data.tiers[k];
              return (
                <Tr key={k}>
                  <Td className="font-semibold">{tl(k)} ({fmt.num(v.agents)})</Td>
                  <Td className={cx("tabular", v.net_benefit_95 < 0 ? "text-high" : "text-ok")}>{money(v.net_benefit_95)}</Td>
                  <Td className="tabular">{p1(v.optimum.coverage)}</Td><Td className="tabular">{p1(v.optimum.buffer)}</Td><Td className="tabular">{t("eco.up.fmt", { n: fmt.num(v.optimum.up, 2) })}</Td>
                  <Td className={cx("tabular", v.net_benefit_optimum > 0 ? "text-ok" : "text-high")}>{money(v.net_benefit_optimum)}</Td>
                  <Td className="tabular">{v.breakeven_trip_cost == null ? "–" : fmt.bdt(Math.round(v.breakeven_trip_cost))}</Td>
                  <Td className="tabular">{v.breakeven_multiplier == null ? "–" : `${fmt.num(v.breakeven_multiplier, 1)}x`}</Td>
                  <Td>{sameApplied(k) ? <NeuBadge tone="ok" icon={<CircleCheck size={13} aria-hidden />}>{t("eco.applied.match")}</NeuBadge> : <NeuBadge tone="watch" icon={<TriangleAlert size={13} aria-hidden />}>{t("eco.applied.differs")}</NeuBadge>}</Td>
                </Tr>
              );
            })}
          </tbody>
        </NeuTable>
      </NeuCard>

      <NeuCard className="flex flex-col gap-3">
        <div><h2 className="text-base font-bold">{t("eco.sens.title")}</h2><p className="text-xs text-muted">{t("eco.sens.sub")}</p></div>
        <NeuTable caption={t("eco.sens.title")}>
          <thead><tr><Th>&nbsp;</Th>{sensCols.map((m) => <Th key={m}>{t("eco.sens.col", { m: fmt.num(m) })}</Th>)}</tr></thead>
          <tbody>
            {sensRows.map((ts) => (
              <Tr key={ts}>
                <Td className="font-semibold">{t("eco.sens.row", { scale: fmt.num(ts, 2) })}</Td>
                {sensCols.map((m) => {
                  const c = data.sensitivity.find((s) => s.trip_scale === ts && s.multiplier === m);
                  return (
                    <Td key={m} className="tabular text-xs">
                      {c ? <span className="flex flex-col gap-0.5"><span className="font-semibold">{p1(c.coverage)}</span><span className={c.beats_habit ? "text-ok" : "text-high"}>{money(c.net_benefit)} · {c.beats_habit ? t("eco.sens.pays") : t("eco.sens.no")}</span></span> : "–"}
                    </Td>
                  );
                })}
              </Tr>
            ))}
          </tbody>
        </NeuTable>
      </NeuCard>
    </div>
  );
}
