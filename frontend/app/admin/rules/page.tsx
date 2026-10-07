"use client";
import { Save, Trash2, TriangleAlert, Undo2 } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { EmptyState, ErrorState, NeuBadge, NeuButton, NeuCard, NeuInput, NeuSelect, NeuTable, Skeleton, Td, Th, Tr, useToast } from "@/components/neu";
import { api, ApiError } from "@/lib/api";
import type { DictKey } from "@/lib/dict.en";
import { useI18n } from "@/lib/i18n";
import { useSim } from "@/lib/session";
import type { AuditItem, EventItem, RulesView } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Field = { key: string; label: DictKey; pct: boolean };   // pct: stored as a fraction, edited as a percentage
const FIELDS: Field[] = [
  { key: "buffer_frac", label: "rules.buffer", pct: true }, { key: "coverage_prob", label: "rules.coverage", pct: true },
  { key: "min_order_frac", label: "rules.min_order", pct: true }, { key: "high_threshold", label: "rules.high", pct: false },
  { key: "watch_threshold", label: "rules.watch", pct: false }, { key: "recon_tolerance", label: "rules.tol", pct: true },
];

export default function RulesPage() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const { bump } = useSim();
  const { data, error, reload } = useApi<RulesView>("/admin/config", { live: false });
  const { data: events, reload: reloadEvents } = useApi<EventItem[]>("/admin/events", { live: false });
  const { data: audit, reload: reloadAudit } = useApi<AuditItem[]>("/admin/audit?limit=12", { live: false });
  const [vals, setVals] = useState<Record<string, string>>({});
  const [manual, setManual] = useState("");
  const [depMode, setDepMode] = useState<"correlated" | "independent">("correlated");
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const load = (r: RulesView) => {
    const v: Record<string, string> = {};
    for (const f of FIELDS) { const x = r.rules[f.key as keyof RulesView["rules"]] as number; v[f.key] = String(f.pct ? +(x * 100).toFixed(2) : x); }
    setVals(v); setManual(r.rules.manual_report_agents.join(", ")); setDepMode(r.rules.dependence_mode); setErrs({});
  };
  useEffect(() => { if (data) load(data); }, [data]);

  const bounds = (f: Field) => { const [lo, hi] = data!.bounds[f.key]; return f.pct ? [lo * 100, hi * 100] : [lo, hi]; };
  const validate = (): Record<string, string> => {
    const e: Record<string, string> = {};
    for (const f of FIELDS) {
      const n = Number(vals[f.key]); const [lo, hi] = bounds(f);
      if (vals[f.key].trim() === "" || !Number.isFinite(n) || n < lo || n > hi) e[f.key] = t("rules.bounds", { lo: fmt.num(lo, 1), hi: fmt.num(hi, 1) });
    }
    if (!e.watch_threshold && !e.high_threshold && Number(vals.watch_threshold) >= Number(vals.high_threshold)) e.watch_threshold = t("rules.invalid");
    return e;
  };

  const save = async (ev: FormEvent) => {
    ev.preventDefault();
    const e = validate(); setErrs(e);
    if (Object.keys(e).length) { toast(t("rules.invalid"), "error"); return; }
    const body: Record<string, unknown> = {};
    for (const f of FIELDS) body[f.key] = f.pct ? Number(vals[f.key]) / 100 : Number(vals[f.key]);
    body.dependence_mode = depMode;
    body.manual_report_agents = manual.split(",").map((s) => s.trim()).filter(Boolean);
    setBusy(true);
    try { await api("/admin/config", { method: "PUT", body }); toast(t("rules.saved")); reload(); reloadAudit(); bump(); }
    catch (err) { toast(err instanceof ApiError ? err.message : t("common.error"), "error"); } finally { setBusy(false); }
  };
  const restore = () => {
    if (!data) return;
    const d = data.defaults as Record<string, number>;
    const v: Record<string, string> = {};
    for (const f of FIELDS) v[f.key] = String(f.pct ? +(d[f.key] * 100).toFixed(2) : d[f.key]);
    setVals(v); setErrs({});
  };

  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return <div className="flex flex-col gap-5" aria-busy="true"><Skeleton className="h-24" /><Skeleton className="h-96" /></div>;

  return (
    <div className="flex flex-col gap-5">
      <div><h1 className="text-2xl font-extrabold">{t("rules.title")}</h1><p className="max-w-3xl text-sm text-muted">{t("rules.sub")}</p></div>

      <NeuCard>
        <form onSubmit={save} className="flex flex-col gap-5" noValidate>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
            {FIELDS.map((f) => (
              <NeuInput key={f.key} label={`${t(f.label)}${f.pct || f.key.endsWith("threshold") ? " (%)" : ""}`} inputMode="decimal" value={vals[f.key] ?? ""}
                onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} error={errs[f.key]} hint={errs[f.key] ? undefined : t("rules.bounds", { lo: fmt.num(bounds(f)[0], 1), hi: fmt.num(bounds(f)[1], 1) })} />
            ))}
            <NeuSelect label={t("rules.dep")} value={depMode} onChange={(e) => setDepMode(e.target.value as "correlated" | "independent")}>
              <option value="correlated">{t("dep.mode.correlated")}</option>
              <option value="independent">{t("dep.mode.independent")}</option>
            </NeuSelect>
            <NeuInput label={t("rules.manual")} value={manual} onChange={(e) => setManual(e.target.value)} hint={t("rules.manual.help")} />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <NeuButton type="submit" variant="primary" loading={busy} icon={<Save size={18} aria-hidden />}>{t("rules.save")}</NeuButton>
            <NeuButton onClick={restore} icon={<Undo2 size={18} aria-hidden />}>{t("rules.reset")}</NeuButton>
            <span className="text-xs text-muted">{t("rules.hash")}: <code className="font-mono font-bold text-ink">{data.config_hash}</code></span>
          </div>
          <p className="text-xs text-muted">{data.note}</p>
        </form>
      </NeuCard>

      <EventsSection events={events} reload={() => { reloadEvents(); reloadAudit(); bump(); }} />

      <NeuCard className="flex flex-col gap-3">
        <h2 className="text-base font-bold">{t("audit.title")}</h2>
        {!audit ? <Skeleton className="h-32" /> : audit.length === 0 ? <EmptyState message={t("audit.none")} /> : (
          <NeuTable caption={t("audit.title")}>
            <thead><tr><Th>{t("audit.when")}</Th><Th>{t("audit.who")}</Th><Th>{t("audit.what")}</Th></tr></thead>
            <tbody>
              {audit.map((a) => (
                <Tr key={a.id}>
                  <Td className="whitespace-nowrap text-xs text-muted">{a.ts.replace("T", " ").slice(0, 19)}</Td>
                  <Td className="font-semibold">{a.actor}</Td>
                  <Td className="max-w-xl text-xs"><b>{a.action}</b> · {a.entity}{a.entity_id ? ` ${a.entity_id}` : ""} <span className="text-muted">{JSON.stringify(a.detail).slice(0, 140)}</span></Td>
                </Tr>
              ))}
            </tbody>
          </NeuTable>
        )}
      </NeuCard>
    </div>
  );
}

function EventsSection({ events, reload }: { events: EventItem[] | null; reload: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const { sim } = useSim();
  const { data: agents } = useApi<{ agent_id: string; division: string }[]>("/agents", { live: false });
  const divisions = useMemo(() => Array.from(new Set((agents ?? []).map((a) => a.division))).sort(), [agents]);
  const [f, setF] = useState({ scope: "division", target: "", kind: "fair", flow: "both", multiplier: "1.5", start: "", end: "", note: "" });
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (sim) setF((x) => (x.start ? x : { ...x, start: sim.date, end: sim.date })); }, [sim]);
  useEffect(() => { setF((x) => ({ ...x, target: x.scope === "division" ? divisions[0] ?? "" : x.scope === "agent" ? agents?.[0]?.agent_id ?? "" : "" })); }, [f.scope, divisions, agents]);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const m = Number(f.multiplier);
    if (!Number.isFinite(m) || m < 0.1 || m > 5) return setErr(t("rules.bounds", { lo: "0.1", hi: "5" }));
    if (!f.start || !f.end || f.end < f.start) return setErr(t("sim.bad_date"));
    setErr(null);
    try {
      await api("/admin/events", { method: "POST", body: { scope: f.scope, target: f.scope === "all" ? null : f.target, kind: f.kind, flow: f.flow, multiplier: m, start_date: f.start, end_date: f.end, note: f.note || null } });
      toast(t("events.added")); reload();
    } catch (er) { setErr(er instanceof ApiError ? er.message : t("common.error")); }
  };
  const remove = async (id: number) => { try { await api(`/admin/events/${id}`, { method: "DELETE" }); toast(t("events.removed")); reload(); } catch (er) { toast((er as Error).message, "error"); } };

  return (
    <NeuCard className="flex flex-col gap-5">
      <div>
        <div className="flex flex-wrap items-center gap-3"><h2 className="text-lg font-bold">{t("events.title")}</h2>
          <NeuBadge tone="watch" icon={<TriangleAlert size={13} aria-hidden />}>{t("events.badge")}</NeuBadge></div>
        <p className="mt-1 max-w-3xl text-sm text-muted">{t("events.sub")}</p>
      </div>
      <form onSubmit={add} className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4" noValidate>
        <NeuSelect label={t("events.scope")} value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value })}>
          <option value="all">{t("events.scope.all")}</option><option value="division">{t("events.scope.division")}</option><option value="agent">{t("events.scope.agent")}</option>
        </NeuSelect>
        {f.scope !== "all" && (
          <NeuSelect label={t("events.target")} value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })}>
            {f.scope === "division" ? divisions.map((d) => <option key={d}>{d}</option>) : (agents ?? []).map((a) => <option key={a.agent_id}>{a.agent_id}</option>)}
          </NeuSelect>
        )}
        <NeuSelect label={t("events.kind")} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
          {["fair", "road_closure", "flood", "other"].map((k) => <option key={k} value={k}>{t(`events.kind.${k}` as DictKey)}</option>)}
        </NeuSelect>
        <NeuSelect label={t("events.flow")} value={f.flow} onChange={(e) => setF({ ...f, flow: e.target.value })}>
          {["both", "cashout", "cashin"].map((k) => <option key={k} value={k}>{t(`events.flow.${k}` as DictKey)}</option>)}
        </NeuSelect>
        <NeuInput label={t("events.mult")} inputMode="decimal" value={f.multiplier} onChange={(e) => setF({ ...f, multiplier: e.target.value })} hint={t("events.mult.help")} />
        <NeuInput label={t("events.start")} type="date" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} />
        <NeuInput label={t("events.end")} type="date" value={f.end} min={f.start} onChange={(e) => setF({ ...f, end: e.target.value })} />
        <NeuInput label={`${t("events.note")} (${t("common.optional")})`} maxLength={200} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
        <div className="flex flex-col gap-2 md:col-span-2 xl:col-span-4">
          {err && <p role="alert" className="text-sm font-medium text-high">{err}</p>}
          <div><NeuButton type="submit" variant="primary">{t("events.add")}</NeuButton></div>
        </div>
      </form>
      {!events ? <Skeleton className="h-20" /> : events.length === 0 ? <EmptyState message={t("events.none")} /> : (
        <NeuTable caption={t("events.title")}>
          <thead><tr><Th>{t("events.kind")}</Th><Th>{t("events.scope")}</Th><Th>{t("events.mult")}</Th><Th>{t("fc.col.date")}</Th><Th>{t("common.status")}</Th><Th>{t("events.note")}</Th><Th><span className="sr-only">{t("events.remove")}</span></Th></tr></thead>
          <tbody>
            {events.map((e) => (
              <Tr key={e.id} className={e.active ? "" : "opacity-60"}>
                <Td className="font-semibold">{t(`events.kind.${e.kind}` as DictKey)}</Td>
                <Td>{e.scope === "all" ? t("events.scope.all") : e.target}</Td>
                <Td className="tabular font-bold">×{fmt.num(e.multiplier, 2)} <span className="text-xs font-normal text-muted">({t(`events.flow.${e.flow}` as DictKey)})</span></Td>
                <Td className="whitespace-nowrap text-xs">{fmt.dateTiny(e.start_date)} – {fmt.dateTiny(e.end_date)}</Td>
                <Td><NeuBadge tone={e.active ? "watch" : "neutral"}>{e.active ? t("events.active") : t("events.inactive")}</NeuBadge><div className="mt-1 max-w-48 text-[11px] text-muted">{e.label}</div></Td>
                <Td className="max-w-48 text-xs">{e.note}</Td>
                <Td>{e.active && <NeuButton variant="danger" className="!px-0" aria-label={t("events.remove")} title={t("events.remove")} onClick={() => remove(e.id)}><Trash2 size={17} aria-hidden /></NeuButton>}</Td>
              </Tr>
            ))}
          </tbody>
        </NeuTable>
      )}
    </NeuCard>
  );
}
