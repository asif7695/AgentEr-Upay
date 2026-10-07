"use client";
import { Map as MapIcon, Route, Save, TriangleAlert, Truck } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { EmptyState, ErrorState, NeuBadge, NeuButton, NeuCard, NeuInput, NeuStat, NeuTable, Skeleton, Td, Th, Tr, cx, useToast } from "@/components/neu";
import { api, ApiError } from "@/lib/api";
import type { DictKey } from "@/lib/dict.en";
import { useI18n } from "@/lib/i18n";
import type { RouteView, RoutingEvidence } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const LINES = ["var(--c-a)", "var(--c-b)", "var(--accent-2)", "var(--ok)", "var(--high)", "var(--muted)"];
const W = 640, H = 380, PAD = 36;

/** Distributor routes for today's optimised plan: map, routes with arrival times, what cannot be served, and evidence. */
export function RoutesView() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const { data, error, reload } = useApi<RouteView>("/admin/routes");
  const { data: evid } = useApi<RoutingEvidence>("/admin/routing-evidence", { live: false });
  const [div, setDiv] = useState<string>("");
  const [vals, setVals] = useState({ vehicles: "", cash: "", speed: "", service: "", day: "" });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!data) return;
    const s = data.settings;
    setVals({ vehicles: String(s.vehicles_per_division), cash: String(s.vehicle_cash_limit), speed: String(s.speed_kmh), service: String(s.service_minutes), day: String(s.day_hours) });
    setErrs({});
    setDiv((d) => (data.divisions.some((x) => x.division === d) ? d : data.divisions[0]?.division ?? ""));
  }, [data]);

  const cur = data?.divisions.find((d) => d.division === div);
  const proj = useMemo(() => {
    if (!cur) return null;
    const pts = [[cur.depot.lat, cur.depot.lon], ...cur.routes.flatMap((r) => r.stops.map((s) => [s.lat, s.lon]))];
    const la0 = pts.reduce((a, p) => a + p[0], 0) / pts.length, k = Math.cos((la0 * Math.PI) / 180);
    const xs = pts.map((p) => p[1] * k), ys = pts.map((p) => -p[0]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const sc = Math.min((W - 2 * PAD) / Math.max(x1 - x0, 1e-6), (H - 2 * PAD) / Math.max(y1 - y0, 1e-6));
    return (lat: number, lon: number) => [PAD + (lon * k - x0) * sc + (W - 2 * PAD - (x1 - x0) * sc) / 2, PAD + (-lat - y0) * sc + (H - 2 * PAD - (y1 - y0) * sc) / 2] as const;
  }, [cur]);

  if (error) return <ErrorState message={error.status === 0 ? t("common.network") : error.message} onRetry={reload} />;
  if (!data) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-28" /><Skeleton className="h-80" /></div>;

  const dur = (m: number) => t("routes.dur", { h: fmt.num(Math.floor(m / 60)), m: fmt.num(Math.round(m % 60)) });
  const save = async (ev: FormEvent) => {
    ev.preventDefault();
    const e: Record<string, string> = {}, b = data.bounds;
    const num = (k: string, v: string, key: string) => { const [lo, hi] = b[key]; const n = Number(v); if (v.trim() === "" || !Number.isFinite(n) || n < lo || n > hi) e[k] = t("rules.bounds", { lo: fmt.num(lo), hi: fmt.num(hi) }); };
    num("vehicles", vals.vehicles, "vehicles_per_division"); num("cash", vals.cash, "vehicle_cash_limit"); num("speed", vals.speed, "speed_kmh"); num("service", vals.service, "service_minutes"); num("day", vals.day, "day_hours");
    setErrs(e);
    if (Object.keys(e).length) { toast(t("rules.invalid"), "error"); return; }
    setBusy(true);
    try {
      await api("/admin/routes/settings", { method: "PUT", body: { vehicles_per_division: Math.round(Number(vals.vehicles)), vehicle_cash_limit: Number(vals.cash), speed_kmh: Number(vals.speed), service_minutes: Number(vals.service), day_hours: Number(vals.day) } });
      toast(t("routes.saved")); reload();
    } catch (err) { toast(err instanceof ApiError ? err.message : t("common.error"), "error"); } finally { setBusy(false); }
  };

  const T = data.totals;
  const savePct = T.naive_km > 0 ? (100 * T.saving_km) / T.naive_km : 0;
  const prioTone = (w: number) => (w >= 3 ? "high" : w >= 2 ? "watch" : "neutral") as "high" | "watch" | "neutral";

  return (
    <div className="flex flex-col gap-5">
      <div><h2 className="flex items-center gap-2 text-lg font-bold"><Route size={18} aria-hidden className="text-accent" />{t("routes.title")}</h2><p className="mt-1 max-w-3xl text-sm text-muted">{t("routes.sub")}</p></div>
      <p role="note" className="neu-inset flex items-start gap-2 p-3 text-xs text-muted"><TriangleAlert size={15} className="mt-0.5 shrink-0" aria-hidden />{t("routes.synthetic")}</p>

      <NeuCard>
        <form onSubmit={save} className="flex flex-col gap-4" noValidate>
          <h3 className="text-base font-bold">{t("routes.settings.title")}</h3>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <NeuInput label={t("routes.vehicles")} inputMode="numeric" value={vals.vehicles} onChange={(e) => setVals({ ...vals, vehicles: e.target.value })} error={errs.vehicles} />
            <NeuInput label={t("routes.cash_limit")} inputMode="numeric" value={vals.cash} onChange={(e) => setVals({ ...vals, cash: e.target.value })} error={errs.cash} />
            <NeuInput label={t("routes.speed")} inputMode="decimal" value={vals.speed} onChange={(e) => setVals({ ...vals, speed: e.target.value })} error={errs.speed} />
            <NeuInput label={t("routes.service")} inputMode="decimal" value={vals.service} onChange={(e) => setVals({ ...vals, service: e.target.value })} error={errs.service} />
            <NeuInput label={t("routes.day")} inputMode="decimal" value={vals.day} onChange={(e) => setVals({ ...vals, day: e.target.value })} error={errs.day} />
          </div>
          <div><NeuButton type="submit" variant="primary" loading={busy} icon={<Save size={16} aria-hidden />}>{t("routes.save")}</NeuButton></div>
        </form>
      </NeuCard>

      <section aria-label="KPIs" className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <NeuStat label={t("routes.kpi.stops")} value={T.stops} format={fmt.num} fill="blue" icon={<MapIcon size={18} />} note={`${fmt.num(T.vehicles)} ${t("routes.kpi.vehicles").toLowerCase()}`} />
        <NeuStat label={t("routes.kpi.km")} value={Math.round(T.distance_km)} format={(n) => `${fmt.num(n)} km`} icon={<Truck size={18} />} note={t("routes.kpi.km.note", { naive: fmt.num(Math.round(T.naive_km)) })} />
        <NeuStat label={t("routes.kpi.saving")} value={savePct} format={(n) => fmt.pct(n, 0)} tone="ok" note={`${fmt.num(Math.round(T.saving_km))} km`} />
        <NeuStat label={t("routes.kpi.unrouted")} value={T.unrouted} format={fmt.num} tone={T.unrouted ? "watch" : "ink"} icon={<TriangleAlert size={18} />} />
      </section>

      {data.divisions.length === 0 ? <EmptyState message={t("routes.none")} /> : (
        <NeuCard className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2" role="tablist" aria-label={t("routes.title")}>
            {data.divisions.map((d) => (
              <button key={d.division} role="tab" aria-selected={d.division === div} onClick={() => setDiv(d.division)}
                className={cx("min-h-11 rounded-xl px-4 text-sm font-semibold", d.division === div ? "neu-inset text-accent" : "neu-raised-sm")}>{d.division}</button>
            ))}
          </div>
          {cur && proj && (
            <>
              <div className="neu-inset p-2">
                <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={t("routes.map", { division: cur.division })}>
                  {cur.routes.map((r, ri) => {
                    const pts = [proj(cur.depot.lat, cur.depot.lon), ...r.stops.map((s) => proj(s.lat, s.lon)), proj(cur.depot.lat, cur.depot.lon)];
                    return <polyline key={r.vehicle} points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke={LINES[ri % LINES.length]} strokeWidth={2.5} strokeDasharray={ri % 2 ? "6 4" : undefined} strokeLinejoin="round" />;
                  })}
                  {cur.routes.flatMap((r, ri) => r.stops.map((s, i) => {
                    const [x, y] = proj(s.lat, s.lon);
                    const fill = s.weight >= 3 ? "var(--high)" : s.weight >= 2 ? "var(--watch)" : "var(--surface)";
                    return (
                      <g key={s.key}>
                        <circle cx={x} cy={y} r={13} fill={fill} stroke={LINES[ri % LINES.length]} strokeWidth={2.5} />
                        <text x={x} y={y + 4} textAnchor="middle" fontSize={12} fontWeight={700} fill={s.weight >= 2 ? "#fff" : "var(--text)"}>{fmt.num(i + 1)}</text>
                        <text x={x + 17} y={y + 4} fontSize={11} fill="var(--muted)">{s.agent_id}</text>
                      </g>
                    );
                  }))}
                  {(() => { const [x, y] = proj(cur.depot.lat, cur.depot.lon); return <g><rect x={x - 9} y={y - 9} width={18} height={18} rx={4} fill="var(--accent-2)" stroke="var(--text)" strokeWidth={2} /><text x={x + 14} y={y + 4} fontSize={11} fontWeight={700} fill="var(--text)">{t("routes.depot")}</text></g>; })()}
                </svg>
              </div>
              {cur.routes.map((r, ri) => (
                <div key={r.vehicle} className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="flex items-center gap-2 text-sm font-bold"><span aria-hidden className="inline-block h-1 w-6 rounded" style={{ background: LINES[ri % LINES.length] }} />{t("routes.vehicle", { n: fmt.num(r.vehicle) })}</h3>
                    <span className="text-xs text-muted">{t("routes.route.sub", { km: fmt.num(Math.round(r.distance_km)), dur: dur(r.duration_min), out: fmt.bdt(r.cash_out), back: fmt.bdt(r.cash_in) })}</span>
                  </div>
                  <NeuTable caption={t("routes.vehicle", { n: fmt.num(r.vehicle) })}>
                    <thead><tr><Th>{t("routes.col.stop")}</Th><Th>{t("common.agent")}</Th><Th>{t("common.type")}</Th><Th>{t("common.amount")}</Th><Th>{t("routes.col.eta")}</Th><Th>{t("routes.col.leg")}</Th><Th>{t("routes.col.priority")}</Th></tr></thead>
                    <tbody>
                      {r.stops.map((s, i) => (
                        <Tr key={s.key}>
                          <Td className="tabular font-bold">{fmt.num(i + 1)}</Td>
                          <Td><Link href={`/admin/agents/${s.agent_id}`} className="font-extrabold text-accent hover:underline">{s.agent_id}</Link></Td>
                          <Td>{s.kind === "cash" ? t("term.cash") : t("term.efloat")}</Td>
                          <Td className="tabular font-semibold">{fmt.bdt(s.amount)}</Td>
                          <Td className="tabular whitespace-nowrap">{dur(s.eta_min)}</Td>
                          <Td className="tabular">{fmt.num(Math.round(s.leg_km))} km</Td>
                          <Td><NeuBadge tone={prioTone(s.weight)}>{t(`routes.prio.${Math.round(s.weight)}` as DictKey)}</NeuBadge></Td>
                        </Tr>
                      ))}
                    </tbody>
                  </NeuTable>
                </div>
              ))}
              {cur.unrouted.length > 0 && (
                <div className="neu-inset flex flex-col gap-1 p-3" role="status">
                  <h3 className="flex items-center gap-2 text-sm font-bold text-watch"><TriangleAlert size={15} aria-hidden />{t("routes.unrouted")}</h3>
                  {cur.unrouted.map((u) => <p key={u.key} className="text-sm"><b>{u.agent_id}</b> · {u.kind === "cash" ? t("term.cash") : t("term.efloat")} {fmt.bdt(u.amount)} · <span className="text-muted">{t(`routes.reason.${u.reason}` as DictKey)}</span></p>)}
                </div>
              )}
            </>
          )}
        </NeuCard>
      )}

      {evid && (
        <NeuCard className="flex flex-col gap-3">
          <div><h3 className="text-base font-bold">{t("routes.evidence.title")}</h3><p className="text-xs text-muted">{t("routes.evidence.sub")}</p></div>
          <NeuTable caption={t("routes.evidence.title")}>
            <thead><tr><Th>{t("routes.evidence.col.fleet")}</Th><Th>{t("routes.evidence.col.km")}</Th><Th>{t("routes.evidence.col.id")}</Th><Th>{t("routes.evidence.col.save")}</Th><Th>{t("routes.evidence.col.wait")}</Th></tr></thead>
            <tbody>
              {evid.rows.map((r) => (
                <Tr key={r.vehicles_per_division}>
                  <Td className="tabular font-semibold">{fmt.num(r.vehicles_per_division)}</Td><Td className="tabular">{fmt.num(r.optimised_km)} km</Td><Td className="tabular">{fmt.num(r.id_order_km)} km</Td>
                  <Td className="tabular font-bold text-ok">{fmt.pct(r.saving_vs_id_order_pct, 0)}</Td><Td className="tabular font-bold text-ok">{fmt.pct(r.priority_waiting_saving_pct, 0)}</Td>
                </Tr>
              ))}
            </tbody>
          </NeuTable>
          <p className="text-xs text-muted">{data.note}</p>
        </NeuCard>
      )}
    </div>
  );
}
