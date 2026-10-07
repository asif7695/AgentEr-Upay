"use client";
import { Check, CheckCheck, Clock, Landmark, Truck, TriangleAlert, XCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { OptimisedPlan } from "@/components/dispatch/OptimisedPlan";
import { EmptyState, ErrorState, NeuBadge, NeuButton, NeuCard, NeuInput, NeuModal, NeuStat, NeuTable, NeuTabs, Skeleton, StatusBadge, Td, Th, Tr, cx, useToast } from "@/components/neu";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSim } from "@/lib/session";
import type { DispatchItem, DispatchPlan, Order } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function DispatchPage() {
  const { t, fmt } = useI18n();
  const { sim } = useSim();
  const toast = useToast();
  const { data, error, reload } = useApi<DispatchPlan>("/admin/dispatch-plan");
  const { data: orders, reload: reloadOrders } = useApi<Order[]>("/admin/orders");
  const [sched, setSched] = useState<DispatchItem | null>(null);
  const [schedDate, setSchedDate] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [tab, setTab] = useState<"opt" | "rule">("opt");

  const refresh = () => { reload(); reloadOrders(); };
  const act = async (key: string, fn: () => Promise<unknown>, okMsg: string) => {
    setBusy(key);
    try { await fn(); toast(okMsg); refresh(); } catch (e) { toast(e instanceof ApiError ? e.message : t("common.error"), "error"); } finally { setBusy(null); }
  };
  const ack = (i: DispatchItem) => act(`${i.agent_id}${i.kind}`, () => api("/admin/orders", { method: "POST", body: { agent_id: i.agent_id, kind: i.kind, amount: i.amount, due_date: i.by_date, order_type: i.order_type, status: "acknowledged" } }), t("disp.created"));
  const patch = (o: Order, body: object, k: string) => act(`${o.agent_id}${o.kind}${k}`, () => api(`/admin/orders/${o.id}`, { method: "PATCH", body }), t("disp.updated"));

  if (error) return <ErrorState message={error.status === 0 ? t("common.network") : error.message} onRetry={reload} />;
  if (!data) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-24" /><Skeleton className="h-64" /><Skeleton className="h-64" /></div>;

  const allItems = data.divisions.flatMap((d) => d.items);
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-extrabold">{t("disp.title")}</h1>
        <p className="text-sm text-muted">{t("disp.sub", { date: fmt.dateLong(data.next_working_day) })}</p>
      </div>
      <NeuTabs label={t("disp.title")} value={tab} onChange={setTab} tabs={[{ id: "opt", label: t("alloc.tab.opt") }, { id: "rule", label: t("alloc.tab.rule") }]} />
      {tab === "opt" && <OptimisedPlan onOrders={refresh} />}
      {tab === "rule" && <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <NeuStat label={t("disp.cash_total")} value={data.totals.cash} format={fmt.bdt} tone="accent" note={t("fc.rec.cash_meaning")} />
        <NeuStat label={t("disp.ef_total")} value={data.totals.efloat} format={fmt.bdt} tone="accent" note={t("fc.rec.efloat_meaning")} />
        <NeuStat label={t("disp.emergency")} value={data.totals.emergency} format={fmt.num} tone={data.totals.emergency ? "high" : "ink"} icon={<TriangleAlert size={18} />} />
        <NeuStat label={t("disp.orders")} value={data.totals.orders} format={fmt.num} icon={<Truck size={18} />} note={`${fmt.num(allItems.length)} ${t("disp.title").toLowerCase()}`} />
      </div>

      {data.divisions.length === 0 && <EmptyState message={t("disp.no_items")} />}

      {data.divisions.map((d) => (
        <NeuCard key={d.division} className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-bold">{d.division}</h2>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <NeuBadge tone="accent">{t("term.cash")}: {fmt.bdt(d.total_cash)}</NeuBadge>
              <NeuBadge tone="accent">{t("term.efloat")}: {fmt.bdt(d.total_efloat)}</NeuBadge>
              {d.needs_capital.length > 0 && <NeuBadge tone="watch" icon={<Landmark size={13} aria-hidden />}>{t("disp.needs_capital", { agents: d.needs_capital.join(", ") })}</NeuBadge>}
            </div>
          </div>
          <NeuTable caption={d.division}>
            <thead><tr><Th>{t("common.agent")}</Th><Th>{t("common.type")}</Th><Th>{t("common.amount")}</Th><Th>{t("disp.by")}</Th><Th>{t("disp.risk")}</Th><Th>{t("common.status")}</Th><Th>{t("disp.orders_log")}</Th></tr></thead>
            <tbody>
              {d.items.map((i) => {
                const o = i.order; const k = `${i.agent_id}${i.kind}`;
                return (
                  <Tr key={k} className={cx(o?.status === "done" && "opacity-70")}>
                    <Td><Link href={`/admin/agents/${i.agent_id}`} className="font-extrabold text-accent hover:underline">{i.agent_id}</Link></Td>
                    <Td>
                      <div className="font-semibold">{i.kind === "cash" ? t("term.cash") : t("term.efloat")}</div>
                      <div className="max-w-52 text-xs text-muted">{i.kind === "cash" ? t("fc.rec.cash_meaning") : t("fc.rec.efloat_meaning")}</div>
                    </Td>
                    <Td className="tabular text-base font-extrabold">{fmt.bdt(i.amount)}{i.float_insufficient && <NeuBadge tone="watch" className="ml-2" icon={<Landmark size={12} aria-hidden />}>{t("tbl.needs_capital")}</NeuBadge>}</Td>
                    <Td className="whitespace-nowrap">
                      <div className="font-semibold">{fmt.date(i.by_date)}</div>
                      <NeuBadge className="mt-1" tone={i.urgent ? "accent" : "neutral"} icon={<Clock size={12} aria-hidden />}>{i.urgent ? t("disp.urgent") : t("disp.later")}</NeuBadge>
                    </Td>
                    <Td><StatusBadge status={i.status} size="sm" label={fmt.pct(i.risk_pct)} />{i.likely_runout_date && <div className="mt-1 text-xs text-muted">{t("disp.runout")} {fmt.date(i.likely_runout_date)}</div>}</Td>
                    <Td>
                      {i.order_type === "emergency"
                        ? <NeuBadge tone="high" icon={<TriangleAlert size={12} aria-hidden />}>{t("order.emergency")}</NeuBadge>
                        : <NeuBadge icon={<Check size={12} aria-hidden />}>{t("order.planned")}</NeuBadge>}
                      {o && <div className="mt-1"><NeuBadge tone={o.status === "done" ? "ok" : "accent"}>{t(`disp.status.${o.status}` as const)}{o.scheduled_for && o.status === "scheduled" ? ` · ${fmt.dateTiny(o.scheduled_for)}` : ""}</NeuBadge></div>}
                    </Td>
                    <Td>
                      <div className="flex flex-wrap gap-2">
                        {!o && <NeuButton variant="primary" loading={busy === k} onClick={() => ack(i)} icon={<Check size={16} aria-hidden />}>{t("disp.ack")}</NeuButton>}
                        {o && (o.status === "acknowledged" || o.status === "proposed") && <NeuButton onClick={() => { setSched(i); setSchedDate(i.by_date); }} icon={<Clock size={16} aria-hidden />}>{t("disp.schedule")}</NeuButton>}
                        {o && (o.status === "scheduled" || o.status === "acknowledged") && <NeuButton loading={busy === `${k}done`} onClick={() => patch(o, { status: "done" }, "done")} icon={<CheckCheck size={16} aria-hidden />}>{t("disp.done")}</NeuButton>}
                        {o && o.status !== "done" && <NeuButton variant="danger" className="!px-0" aria-label={t("disp.cancel")} title={t("disp.cancel")} onClick={() => patch(o, { status: "cancelled" }, "x")}><XCircle size={18} aria-hidden /></NeuButton>}
                      </div>
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </NeuTable>
        </NeuCard>
      ))}
      <p className="text-xs text-muted">{data.note}</p>
      </>}

      <NeuCard className="flex flex-col gap-3">
        <h2 className="text-base font-bold">{t("disp.orders_log")}</h2>
        {!orders ? <Skeleton className="h-24" /> : orders.length === 0 ? <EmptyState message={t("common.empty")} /> : (
          <NeuTable caption={t("disp.orders_log")}>
            <thead><tr><Th>#</Th><Th>{t("common.agent")}</Th><Th>{t("common.type")}</Th><Th>{t("common.amount")}</Th><Th>{t("disp.by")}</Th><Th>{t("common.status")}</Th><Th>{t("fc.col.date")}</Th></tr></thead>
            <tbody>
              {orders.map((o) => (
                <Tr key={o.id}>
                  <Td className="tabular">{fmt.num(o.id)}</Td><Td className="font-bold">{o.agent_id}</Td>
                  <Td>{o.kind === "cash" ? t("term.cash") : t("term.efloat")} · {o.order_type === "emergency" ? t("order.emergency") : t("order.planned")}</Td>
                  <Td className="tabular font-semibold">{fmt.bdt(o.amount)}</Td><Td>{fmt.date(o.due_date)}</Td>
                  <Td><NeuBadge tone={o.status === "done" ? "ok" : o.status === "cancelled" ? "neutral" : "accent"}>{t(`disp.status.${o.status}` as const)}</NeuBadge></Td>
                  <Td className="text-xs text-muted">{fmt.dateTiny(o.plan_date)}</Td>
                </Tr>
              ))}
            </tbody>
          </NeuTable>
        )}
      </NeuCard>

      <NeuModal open={!!sched} onClose={() => setSched(null)} title={t("disp.schedule")}
        footer={<><NeuButton onClick={() => setSched(null)}>{t("common.cancel")}</NeuButton>
          <NeuButton variant="primary" disabled={!schedDate || (sim ? schedDate < sim.date : false)} onClick={() => { const i = sched!; setSched(null); patch(i.order!, { status: "scheduled", scheduled_for: schedDate }, "s"); }}>{t("common.confirm")}</NeuButton></>}>
        {sched && (
          <div className="flex flex-col gap-3">
            <p className="text-sm">{sched.agent_id} · {sched.kind === "cash" ? t("term.cash") : t("term.efloat")} · <b>{fmt.bdt(sched.amount)}</b></p>
            <NeuInput type="date" label={t("disp.sched_for")} value={schedDate} min={sim?.date} onChange={(e) => setSchedDate(e.target.value)} />
            <p className="text-xs text-muted">{t("disp.by")}: {fmt.date(sched.by_date)}</p>
          </div>
        )}
      </NeuModal>
    </div>
  );
}
