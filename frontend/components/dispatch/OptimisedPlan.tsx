"use client";
import { Check, Network, RotateCcw, Save, ShieldCheck, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, GRID } from "@/components/charts/common";
import { ErrorState, NeuBadge, NeuButton, NeuCard, NeuInput, NeuStat, NeuTable, NeuToggle, Skeleton, StatusBadge, Td, Th, Tr, cx, useToast } from "@/components/neu";
import { api, ApiError } from "@/lib/api";
import type { DictKey } from "@/lib/dict.en";
import { useI18n } from "@/lib/i18n";
import { useSim } from "@/lib/session";
import type { AllocationPlan, AllocTotals } from "@/lib/types";
import { useApi } from "@/lib/useApi";

/** Network-wide allocation: what the distributor can deliver today -> the best amount for every agent. Recommendations only. */
export function OptimisedPlan({ onOrders }: { onOrders: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const { bump } = useSim();
  const { data, error, reload } = useApi<AllocationPlan>("/admin/allocation");
  const [plan, setPlan] = useState<AllocationPlan | null>(null);      // a re-solved plan (with the admin's amounts) replaces the loaded one
  const [locks, setLocks] = useState<Record<string, string>>({});
  const [vals, setVals] = useState({ cash: "", ef: "", orders: "" });
  const [protect, setProtect] = useState(true);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setPlan(null); setLocks({});
    setVals({ cash: String(data.settings.cash_budget), ef: String(data.settings.efloat_budget), orders: String(data.settings.max_orders_per_division) });
    setProtect(data.settings.protect_high_risk); setErrs({});
  }, [data]);

  if (error) return <ErrorState message={error.status === 0 ? t("common.network") : error.message} onRetry={reload} />;
  if (!data) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-28" /><Skeleton className="h-72" /><Skeleton className="h-72" /></div>;
  const p = plan ?? data;
  const money = (n: number) => `${n < 0 ? "−" : ""}${fmt.bdt(Math.abs(Math.round(n)))}`;
  const lockBody = () => Object.fromEntries(Object.entries(locks).filter(([, v]) => v.trim() !== "" && Number.isFinite(Number(v)) && Number(v) >= 0).map(([k, v]) => [k, Number(v)]));
  const fail = (err: unknown) => toast(err instanceof ApiError ? err.message : t("common.error"), "error");

  const saveSettings = async (ev: FormEvent) => {
    ev.preventDefault();
    const e: Record<string, string> = {}, b = data.bounds ?? {};
    const num = (k: string, v: string, lo: number, hi: number) => { const n = Number(v); if (v.trim() === "" || !Number.isFinite(n) || n < lo || n > hi) e[k] = t("rules.bounds", { lo: fmt.num(lo), hi: fmt.num(hi) }); };
    num("cash", vals.cash, b.cash_budget?.[0] ?? 0, b.cash_budget?.[1] ?? 1e8); num("ef", vals.ef, b.efloat_budget?.[0] ?? 0, b.efloat_budget?.[1] ?? 1e8);
    num("orders", vals.orders, b.max_orders_per_division?.[0] ?? 0, b.max_orders_per_division?.[1] ?? 50);
    setErrs(e);
    if (Object.keys(e).length) { toast(t("rules.invalid"), "error"); return; }
    setBusy("save");
    try {
      await api("/admin/allocation/settings", { method: "PUT", body: { cash_budget: Number(vals.cash), efloat_budget: Number(vals.ef), max_orders_per_division: Math.round(Number(vals.orders)), protect_high_risk: protect } });
      toast(t("alloc.saved")); reload();
    } catch (err) { fail(err); } finally { setBusy(null); }
  };
  const resolve = async () => {
    setBusy("solve");
    try { setPlan(await api<AllocationPlan>("/admin/allocation/solve", { method: "POST", body: { locks: lockBody() } })); } catch (err) { fail(err); } finally { setBusy(null); }
  };
  const approve = async () => {
    setBusy("approve");
    try {
      const r = await api<{ created: unknown[]; skipped: unknown[] }>("/admin/allocation/approve", { method: "POST", body: { locks: lockBody() } });
      toast(t("alloc.approved", { n: fmt.num(r.created.length), skipped: fmt.num(r.skipped.length) })); reload(); onOrders(); bump();
    } catch (err) { fail(err); } finally { setBusy(null); }
  };

  const T = p.totals;
  const col = (title: string, m: AllocTotals, hl = false) => (
    <div className={cx("flex flex-col gap-1 rounded-xl border p-3", hl ? "border-[var(--accent)]" : "border-[var(--border)]")}>
      <h3 className="text-sm font-bold">{title}</h3>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-muted">{t("alloc.col.orders")}</dt><dd className="tabular text-right font-bold">{fmt.num(m.orders)}</dd>
        <dt className="text-muted">{t("alloc.col.unserved")}</dt><dd className="tabular text-right font-bold">{fmt.bdt(Math.round(m.expected_unserved))}</dd>
        <dt className="text-muted">{t("alloc.col.cost")}</dt><dd className="tabular text-right font-bold">{fmt.bdt(Math.round(m.total_cost))}</dd>
        <dt className="text-muted">{t("alloc.col.netcash")}</dt><dd className="tabular text-right font-bold">{money(m.net_cash)}</dd>
        <dt className="text-muted">{t("alloc.col.feasible")}</dt><dd className={cx("text-right font-bold", m.feasible ? "text-ok" : "text-high")}>{m.feasible ? t("common.yes") : t("common.no")}</dd>
      </dl>
    </div>
  );
  const lines = p.lines;
  const opened = lines.filter((l) => l.amount > 0).length;
  const curve = p.budget_curve;

  return (
    <div className="flex flex-col gap-5">
      <div><h2 className="flex items-center gap-2 text-lg font-bold"><Network size={18} aria-hidden className="text-accent" />{t("alloc.title")}</h2><p className="mt-1 max-w-3xl text-sm text-muted">{t("alloc.sub")}</p></div>

      <NeuCard>
        <form onSubmit={saveSettings} className="flex flex-col gap-4" noValidate>
          <div><h3 className="text-base font-bold">{t("alloc.settings.title")}</h3><p className="text-xs text-muted">{t("alloc.placeholder")}</p></div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <NeuInput label={t("alloc.cash_budget")} inputMode="numeric" value={vals.cash} onChange={(e) => setVals({ ...vals, cash: e.target.value })} error={errs.cash} hint={t("alloc.cash_budget.help")} />
            <NeuInput label={t("alloc.ef_budget")} inputMode="numeric" value={vals.ef} onChange={(e) => setVals({ ...vals, ef: e.target.value })} error={errs.ef} />
            <NeuInput label={t("alloc.max_orders")} inputMode="numeric" value={vals.orders} onChange={(e) => setVals({ ...vals, orders: e.target.value })} error={errs.orders} />
          </div>
          <NeuToggle checked={protect} onChange={setProtect} label={t("alloc.protect")} />
          <div><NeuButton type="submit" variant="primary" loading={busy === "save"} icon={<Save size={16} aria-hidden />}>{t("alloc.save")}</NeuButton></div>
        </form>
      </NeuCard>

      {p.note && <p role="status" className="neu-inset flex items-start gap-2 p-3 text-sm font-medium text-watch"><TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden />{t(`alloc.note.${p.note}` as DictKey)}</p>}

      <section aria-label={t("alloc.cmp.title")} className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <NeuStat label={t("alloc.cmp.opt")} value={opened} format={fmt.num} fill="blue" icon={<Network size={18} />} note={t("alloc.col.orders")} />
        <NeuStat label={t("alloc.col.cost")} value={Math.round(T.optimised.total_cost)} format={fmt.bdt} icon={<Check size={18} />} note={`${t("alloc.cmp.simple")}: ${fmt.bdt(Math.round(T.simple.total_cost))}`} />
        <NeuStat label={t("alloc.col.unserved")} value={Math.round(T.optimised.expected_unserved)} format={fmt.bdt} tone={T.optimised.expected_unserved <= T.simple.expected_unserved ? "ok" : "watch"} note={`${t("alloc.cmp.simple")}: ${fmt.bdt(Math.round(T.simple.expected_unserved))}`} />
        <NeuStat label={t("alloc.col.netcash")} value={Math.round(T.optimised.net_cash)} format={money} note={`${t("alloc.cash_budget")}: ${fmt.bdt(p.settings.cash_budget)}`} />
      </section>

      <NeuCard className="flex flex-col gap-3">
        <h3 className="text-base font-bold">{t("alloc.cmp.title")}</h3>
        <p className="text-sm font-semibold">{p.saving_vs_simple > 0 || p.unserved_avoided_vs_simple > 0
          ? t("alloc.headline", { saving: money(Math.max(0, p.saving_vs_simple)), unserved: money(Math.max(0, p.unserved_avoided_vs_simple)), orders: fmt.num(T.optimised.orders), simpleOrders: fmt.num(T.simple.orders) })
          : t("alloc.headline.none")}</p>
        {!T.rule.feasible && <p className="text-sm text-muted">{t("alloc.rule_over", { need: money(T.rule.net_cash), budget: money(p.settings.cash_budget) })}</p>}
        {p.cost_of_protection !== null && p.cost_of_protection > 0 && <p className="flex items-center gap-2 text-sm text-muted"><ShieldCheck size={15} aria-hidden />{t("alloc.protect_cost", { cost: money(p.cost_of_protection) })}</p>}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {col(t("alloc.cmp.rule"), T.rule)}{col(t("alloc.cmp.simple"), T.simple)}{col(t("alloc.cmp.opt"), T.optimised, true)}
        </div>
        <p className="text-xs text-muted">{p.method} {p.assumptions.source}.</p>
      </NeuCard>

      <NeuCard className="flex flex-col gap-3">
        <div><h3 className="text-base font-bold">{t("alloc.curve.title")}</h3><p className="text-xs text-muted">{t("alloc.curve.sub")}</p></div>
        <div className="neu-inset h-64 p-2" role="img" aria-label={t("alloc.curve.title")}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={curve} margin={{ top: 12, right: 16, bottom: 8, left: 8 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="budget" {...AXIS} tickFormatter={(v) => fmt.num(Math.round(v / 1000)) + "k"} />
              <YAxis {...AXIS} width={52} tickFormatter={(v) => fmt.num(v)} domain={["auto", "auto"]} />
              <Tooltip formatter={(v) => fmt.bdt(Math.round(Number(v)))} labelFormatter={(v) => fmt.bdt(Number(v))} contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10 }} />
              <ReferenceLine x={curve.reduce((a, c) => (Math.abs(c.budget - p.settings.cash_budget) < Math.abs(a.budget - p.settings.cash_budget) ? c : a), curve[0]).budget} stroke="var(--muted)" strokeDasharray="4 4"
                label={{ value: t("alloc.curve.current"), position: "top", fill: "var(--muted)", fontSize: 12 }} />
              <Line type="monotone" dataKey="total_cost" stroke="var(--c-a)" strokeWidth={2.5} dot={{ r: 3 }} name={t("alloc.col.cost")} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </NeuCard>

      <NeuCard className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-bold">{t("alloc.lines.title")}</h3>
          <div className="flex flex-wrap gap-2">
            <NeuButton onClick={resolve} loading={busy === "solve"} disabled={Object.keys(lockBody()).length === 0} icon={<RotateCcw size={16} aria-hidden />}>{t("alloc.resolve")}</NeuButton>
            <NeuButton onClick={() => { setLocks({}); setPlan(null); }} disabled={Object.keys(locks).length === 0 && !plan}>{t("alloc.reset")}</NeuButton>
            <NeuButton variant="primary" onClick={approve} loading={busy === "approve"} disabled={opened === 0} icon={<Check size={16} aria-hidden />}>{t("alloc.approve")}</NeuButton>
          </div>
        </div>
        <NeuTable caption={t("alloc.lines.title")}>
          <thead><tr><Th>{t("common.agent")}</Th><Th>{t("common.type")}</Th><Th>{t("disp.risk")}</Th><Th>{t("alloc.col.rule")}</Th><Th>{t("alloc.col.amount")}</Th><Th>{t("alloc.col.lock")}</Th><Th>{t("alloc.col.value")}</Th><Th>{t("alloc.col.why")}</Th></tr></thead>
          <tbody>
            {lines.map((l) => (
              <Tr key={l.key}>
                <Td><Link href={`/admin/agents/${l.agent_id}`} className="font-extrabold text-accent hover:underline">{l.agent_id}</Link><div className="text-xs text-muted">{l.division}</div></Td>
                <Td><div className="font-semibold">{l.kind === "cash" ? t("term.cash") : t("term.efloat")}</div></Td>
                <Td><StatusBadge status={l.status} size="sm" label={fmt.pct(l.risk_pct)} /></Td>
                <Td className="tabular text-muted">{l.rule_amount ? fmt.bdt(l.rule_amount) : "–"}</Td>
                <Td className="tabular text-base font-extrabold">{l.amount ? fmt.bdt(l.amount) : "–"}{l.order && <NeuBadge className="ml-2" tone="accent">{t(`disp.status.${l.order.status}` as DictKey)}</NeuBadge>}</Td>
                <Td className="w-36"><NeuInput aria-label={`${t("alloc.col.lock")} ${l.key}`} inputMode="numeric" placeholder={l.locked ? t("alloc.fixed") : fmt.num(l.amount)} value={locks[l.key] ?? ""} onChange={(e) => setLocks({ ...locks, [l.key]: e.target.value })} className="[&_input]:min-h-10" /></Td>
                <Td className={cx("tabular", l.net_value < 0 ? "text-watch" : l.net_value > 0 ? "text-ok" : "text-muted")}>{l.amount ? money(l.net_value) : "–"}</Td>
                <Td className="max-w-56 text-xs text-muted">{t(`alloc.reason.${l.reason}` as DictKey)}</Td>
              </Tr>
            ))}
          </tbody>
        </NeuTable>
      </NeuCard>
    </div>
  );
}
