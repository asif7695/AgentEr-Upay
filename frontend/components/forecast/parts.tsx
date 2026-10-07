"use client";
import { ArrowDownRight, ArrowUpRight, CalendarClock, CircleCheck, ClipboardEdit, Info, Landmark, ShieldAlert, TriangleAlert, Wallet } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { NeuBadge, NeuCard, NeuGauge, NeuTable, NeuTabs, StatusBadge, Td, Th, Tr, cx } from "@/components/neu";
import type { DictKey } from "@/lib/dict.en";
import { useI18n } from "@/lib/i18n";
import type { Action, Forecast, Reconciliation, Section, WhyItem } from "@/lib/types";

/* ----------------------------------------------------------- action text */
export function useActionText() {
  const { t, fmt } = useI18n();
  return (a: Action): { title: string; sub?: string; icon: ReactNode; tone: "high" | "watch" | "ok" | "accent" } => {
    switch (a.type) {
      case "cash_topup": return { title: t("action.cash_topup", { amount: fmt.num(a.amount), date: fmt.date(a.by_date) }), sub: t("action.cash_topup.sub"), icon: <Wallet size={22} aria-hidden />, tone: a.order_type === "emergency" ? "high" : "accent" };
      case "efloat_topup": return { title: t("action.efloat_topup", { amount: fmt.num(a.amount), date: fmt.date(a.by_date) }), sub: t("action.efloat_topup.sub"), icon: <Wallet size={22} aria-hidden />, tone: a.order_type === "emergency" ? "high" : "accent" };
      case "capital": return { title: t("action.capital", { amount: fmt.num(a.amount) }), sub: t("action.capital.sub"), icon: <Landmark size={22} aria-hidden />, tone: "watch" };
      case "submit_report": return { title: t("action.submit_report"), sub: t("action.submit_report.sub"), icon: <ClipboardEdit size={22} aria-hidden />, tone: "accent" };
      case "verify_report": return { title: t("action.verify_report"), sub: t("action.verify_report.sub", { pct: a.gap_pct == null ? "–" : fmt.num(Math.abs(a.gap_pct), 1) }), icon: <ClipboardEdit size={22} aria-hidden />, tone: "watch" };
      default: return { title: t("action.all_good"), sub: t("action.all_good.sub"), icon: <CircleCheck size={22} aria-hidden />, tone: "ok" };
    }
  };
}

const TONE = { high: "text-high", watch: "text-watch", ok: "text-ok", accent: "text-accent" } as const;

/** "Do this next": the single most useful action (top-ups first), others listed beneath. */
export function ActionCard({ fc, onNavigate }: { fc: Forecast; onNavigate?: (a: Action) => void }) {
  const { t } = useI18n();
  const text = useActionText();
  const [first, ...rest] = fc.actions;
  const p = text(first);
  const late = fc.actions.some((a) => (a.type === "cash_topup" || a.type === "efloat_topup") && a.late);
  const emergency = fc.actions.some((a) => (a.type === "cash_topup" || a.type === "efloat_topup") && a.order_type === "emergency");
  return (
    <NeuCard className="flex flex-col gap-3" aria-labelledby="next-title">
      <div className="flex items-center justify-between gap-2">
        <h2 id="next-title" className="text-xs font-bold uppercase tracking-wide text-muted">{t("home.next")}</h2>
        {emergency && <NeuBadge tone="high" icon={<TriangleAlert size={13} aria-hidden />}>{t("order.emergency")}</NeuBadge>}
      </div>
      <div className="flex items-start gap-3">
        <span className={cx("neu-inset grid h-12 w-12 shrink-0 place-items-center", TONE[p.tone])}>{p.icon}</span>
        <div className="min-w-0">
          <p className="text-lg font-bold leading-snug">{p.title}</p>
          {p.sub && <p className="mt-1 text-sm text-muted">{p.sub}</p>}
        </div>
      </div>
      {late && <p className="flex items-start gap-2 text-sm font-medium text-watch"><ShieldAlert size={16} className="mt-0.5 shrink-0" aria-hidden />{t("action.late")}</p>}
      {rest.filter((a) => a.type !== "all_good").map((a, i) => {
        const x = text(a);
        return (
          <button key={i} onClick={() => onNavigate?.(a)} className="neu-flat flex min-h-11 items-center gap-3 px-3 py-2 text-left text-sm font-semibold">
            <span className={TONE[x.tone]}>{x.icon}</span><span>{x.title}</span>
          </button>
        );
      })}
    </NeuCard>
  );
}

/* ------------------------------------------------------------ reconciliation */
export function ReconBadge({ rec }: { rec: Pick<Reconciliation, "status"> }) {
  const { t } = useI18n();
  const tone = rec.status === "confirmed" ? "ok" : "watch";
  const Icon = rec.status === "confirmed" ? CircleCheck : TriangleAlert;
  return <NeuBadge tone={tone} icon={<Icon size={13} aria-hidden />}>{t(`rec.status.${rec.status}` as const)}</NeuBadge>;
}

export function ReconCard({ rec, tolerance = 10, compact = false }: { rec: Reconciliation; tolerance?: number; compact?: boolean }) {
  const { t, fmt } = useI18n();
  const warn = rec.status === "pending" || rec.status === "missing" ? t("rec.warn.estimated") : rec.status === "needs_verification" ? t("rec.warn.verify", { tol: fmt.num(tolerance) }) : null;
  return (
    <NeuCard className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-bold">{t("rec.title")}</h3>
        <ReconBadge rec={rec} />
      </div>
      {warn && <p role="status" className="neu-inset flex items-start gap-2 p-3 text-sm font-medium text-watch"><TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden />{warn}</p>}
      {!compact && (
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <Fact label={t("rec.ledger")} value={fmt.bdt(rec.ledger_cash)} />
          <Fact label={t("rec.reported")} value={rec.reported_cash == null ? t("rec.none_yet") : fmt.bdt(rec.reported_cash)} />
          <Fact label={t("rec.gap")} value={rec.gap == null ? "–" : `${fmt.signed(rec.gap)}${rec.gap_pct == null ? "" : ` (${fmt.signed(rec.gap_pct * 100)}%)`}`} />
          <Fact label={t("rec.used")} value={`${fmt.bdt(rec.cash_used)} · ${t(`rec.source.${rec.cash_source}` as const)}`} />
        </dl>
      )}
    </NeuCard>
  );
}
export function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs font-semibold text-muted">{label}</dt><dd className="tabular mt-0.5 font-bold">{value}</dd></div>;
}

/* -------------------------------------------------------------- risk panel */
function runoutLine(sec: Section, t: ReturnType<typeof useI18n>["t"], fmt: ReturnType<typeof useI18n>["fmt"]) {
  return sec.likely_runout_date ? t("fc.runout.likely", { date: fmt.date(sec.likely_runout_date) }) : t("fc.runout.none");
}
export function RiskPanel({ fc, size = 168 }: { fc: Forecast; size?: number }) {
  const { t, fmt } = useI18n();
  const secs: [keyof Pick<Forecast, "cash" | "efloat">, string][] = [["cash", "gauge.cash"], ["efloat", "gauge.efloat"]];
  return (
    <NeuCard className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 sm:gap-8">
        {secs.map(([k, title]) => {
          const s = fc[k];
          return (
            <NeuGauge key={k} size={size} value={s.risk_pct} status={s.status} title={t(title as "gauge.cash")} thresholds={{ watch: fc.thresholds.watch, high: fc.thresholds.high }}
              subtitle={t("gauge.sub", { n: s.window_days })}
              footer={<>
                <span className="text-xs font-semibold">{t("gauge.of_cap", { pct: fmt.num(s.pct_of_capacity) })} · {fmt.bdt(s.current)}</span>
                <span className="inline-flex items-center gap-1 text-xs font-semibold"><CalendarClock size={13} aria-hidden />{runoutLine(s, t, fmt)}</span>
                <span className="text-xs text-muted">{t("fc.risk.7d")}: {fmt.pct(s.risk_pct_7d)}</span>
              </>} />
          );
        })}
      </div>
      <p className="neu-inset flex items-start gap-2 p-3 text-xs text-muted"><Info size={15} className="mt-0.5 shrink-0" aria-hidden />{t("fc.risk.why_two")}</p>
      {fc.dependence.risk_independent && fc.dependence.risk_correlated && (
        <div className="neu-inset flex flex-col gap-1 p-3 text-xs" aria-label={t("dep.title")}>
          <span className="font-bold">{t("dep.title")}</span>
          {(["cash", "efloat"] as const).map((k) => (
            <span key={k} className="text-muted">
              {t(k === "cash" ? "gauge.cash" : "gauge.efloat")}: {t("dep.line", { a: fmt.pct(fc.dependence.risk_independent![k]), b: fmt.pct(fc.dependence.risk_correlated![k]) })}
            </span>
          ))}
          <span className="text-muted">{t("dep.active", { mode: t(`dep.mode.${fc.dependence.mode}` as DictKey) })} · {t("model.active", { model: t(`model.choice.${fc.model.choice}` as DictKey) })}</span>
        </div>
      )}
    </NeuCard>
  );
}

/* --------------------------------------------------- recommended inventory */
function Meter({ current, recommended, capacity, label }: { current: number; recommended: number; capacity: number; label: string }) {
  const max = Math.max(capacity, current, recommended) * 1.02;
  const pct = (x: number) => `${Math.max(0, Math.min(100, (x / max) * 100))}%`;
  return (
    <div className="neu-inset-sm relative h-4 w-full overflow-visible rounded-full" role="img" aria-label={label} style={{ borderRadius: 9999 }}>
      <div className="absolute inset-y-0.5 left-0.5 rounded-full" style={{ width: pct(current), background: "var(--accent-fill)", borderRadius: 9999, minWidth: 6 }} />
      <div className="absolute -top-1.5 h-7 w-0.5 rounded" style={{ left: pct(recommended), background: "var(--accent-2)", boxShadow: "0 0 0 1.5px var(--text)" }} aria-hidden />
    </div>
  );
}

export function RecommendPanel({ fc }: { fc: Forecast }) {
  const { t, fmt } = useI18n();
  const rows: { key: "cash" | "efloat"; title: string; meaning: string }[] = [
    { key: "cash", title: t("fc.rec.cash"), meaning: t("fc.rec.cash_meaning") },
    { key: "efloat", title: t("fc.rec.efloat"), meaning: t("fc.rec.efloat_meaning") },
  ];
  return (
    <NeuCard className="flex flex-col gap-5">
      <h3 className="text-base font-bold">{t("fc.rec.title")}</h3>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {rows.map(({ key, title, meaning }) => {
          const s = fc[key];
          const short = s.gap_vs_current > 0;
          return (
            <div key={key} className="flex flex-col gap-3">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-bold">{title}</span>
                <span className="text-xs text-muted">{t("term.capacity")} {fmt.bdt(s.capacity)}</span>
              </div>
              <Meter current={s.current} recommended={s.recommended_level} capacity={s.capacity} label={`${t("fc.rec.current")} ${fmt.bdt(s.current)}, ${t("fc.rec.recommended")} ${fmt.bdt(s.recommended_level)}`} />
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <Fact label={t("fc.rec.current")} value={`${fmt.bdt(s.current)} (${fmt.pct(s.pct_of_capacity)})`} />
                <Fact label={t("fc.rec.recommended")} value={fmt.bdt(s.recommended_level)} />
              </dl>
              <p className={cx("text-sm font-semibold", short ? "text-watch" : "text-ok")}>
                {short ? t("fc.rec.short", { amount: fmt.num(s.gap_vs_current) }) : t("fc.rec.above", { amount: fmt.num(-s.gap_vs_current) })}
              </p>
              <div className="neu-inset p-3">
                <div className="text-xs font-semibold text-muted">{t("fc.rec.topup")}</div>
                {s.topup > 0 && s.topup_by_date ? (
                  <>
                    <div className="tabular text-lg font-extrabold">{fmt.bdt(s.topup)} <span className="text-sm font-semibold text-muted">{t("fc.rec.by", { date: fmt.date(s.topup_by_date) })}</span></div>
                    <div className="mt-1 text-xs text-muted">{meaning}</div>
                    {s.topup_late && <div className="mt-1 text-xs font-semibold text-watch">{t("action.late")}</div>}
                  </>
                ) : <div className="text-sm font-semibold text-ok">{t("fc.rec.none")}</div>}
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-xs text-muted">{t("fc.rec.coverage", { n: fc.cash.window_days, p: fmt.num(fc.config.coverage_prob * 100, 1), b: fmt.num(fc.config.buffer_frac * 100) })}</p>
      {fc.capital.insufficient && (
        <div role="status" className="neu-inset flex items-start gap-3 p-4">
          <Landmark size={20} className="mt-0.5 shrink-0 text-watch" aria-hidden />
          <div>
            <p className="font-bold text-watch">{t("fc.rec.capital", { amount: fmt.num(fc.capital.needed) })}</p>
            <p className="mt-1 text-xs text-muted">{t("fc.rec.capital.detail", { req: fmt.num(fc.capital.required_cash + fc.capital.required_efloat), rc: fmt.num(fc.capital.required_cash), re: fmt.num(fc.capital.required_efloat), have: fmt.num(fc.capital.total_float) })}</p>
          </div>
        </div>
      )}
      <p className="text-xs text-muted">{t("fc.unserved")}: <b className="tabular text-ink">{fmt.bdt(fc.expected_unserved.total)}</b> · {t("fc.unserved.note")}</p>
    </NeuCard>
  );
}

/* ------------------------------------------------------------- day table */
export function DayTable({ fc }: { fc: Forecast }) {
  const { t, fmt } = useI18n();
  return (
    <NeuCard className="flex flex-col gap-3">
      <div>
        <h3 className="text-base font-bold">{t("fc.table.title")}</h3>
        <p className="text-xs text-muted">{t("fc.surge.def", { x: fc.config.surge_multiple })}</p>
      </div>
      <NeuTable caption={t("fc.table.title")}>
        <thead>
          <tr>
            <Th rowSpan={2}>{t("fc.col.date")}</Th><Th rowSpan={2}>{t("fc.col.open")}</Th>
            <Th colSpan={4} className="text-center" style={{ color: "var(--c-a)" }}>{t("term.cashout")}</Th>
            <Th colSpan={4} className="text-center" style={{ color: "var(--c-b)" }}>{t("term.cashin")}</Th>
          </tr>
          <tr>
            {[0, 1].flatMap((i) => [t("fc.col.median"), t("fc.col.mean"), t("fc.col.range"), t("fc.col.surge")].map((c, j) => <Th key={`${i}${j}`}>{c}</Th>))}
          </tr>
        </thead>
        <tbody>
          {fc.days.map((d) => (
            <Tr key={d.date} className={!d.is_working_day ? "opacity-85" : undefined}>
              <Td className="whitespace-nowrap font-semibold">{fmt.date(d.date)}</Td>
              <Td><NeuBadge tone={d.is_working_day ? "ok" : "neutral"}>{d.is_working_day ? t("fc.open") : t("fc.closed_short")}{d.is_holiday ? " ★" : ""}</NeuBadge></Td>
              {(["cashout", "cashin"] as const).map((f) => (
                <FlowCells key={f} q={d[f]} />
              ))}
            </Tr>
          ))}
        </tbody>
      </NeuTable>
    </NeuCard>
  );
}
function FlowCells({ q }: { q: Forecast["days"][number]["cashout"] }) {
  const { fmt } = useI18n();
  return (
    <>
      <Td className="tabular font-bold">{fmt.bdt(q.p50)}</Td>
      <Td className="tabular">{fmt.bdt(q.mean)}</Td>
      <Td className="tabular whitespace-nowrap text-muted">{fmt.num(q.p10)} – {fmt.num(q.p90)}</Td>
      <Td className="tabular">{fmt.pct(q.p_surge * 100)}</Td>
    </>
  );
}

/* ------------------------------------------------------------------- why */
export function whySentence(it: WhyItem, t: ReturnType<typeof useI18n>["t"], fmt: ReturnType<typeof useI18n>["fmt"], label: string) {
  const dir = it.bdt >= 0 ? "up" : "down";
  if (it.flag) return t(`fc.why.flag.${it.flag}.${dir}` as const, { label });
  const num = /^-?\d+(\.\d+)?$/.test(it.value) ? fmt.num(parseFloat(it.value), (it.value.split(".")[1] || "").length) : it.value;
  return t(`fc.why.num.${dir}` as const, { label, value: num });
}

export function WhyPanel({ fc }: { fc: Forecast }) {
  const { t, fmt, feature } = useI18n();
  const [flow, setFlow] = useState<"cashout" | "cashin">("cashout");
  const [day, setDay] = useState(0);
  const why = fc.why;
  const items = useMemo(() => why?.[flow]?.[day] ?? [], [why, flow, day]);
  if (!why) return null;
  const base = flow === "cashout" ? why.baseline_cashout[day] : why.baseline_cashin[day];
  return (
    <NeuCard className="flex flex-col gap-4">
      <div>
        <h3 className="text-base font-bold">{t("fc.why.title")}</h3>
        <p className="text-xs text-muted">{t("fc.why.sub")}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <NeuTabs label={t("fc.why.title")} value={flow} onChange={setFlow} tabs={[{ id: "cashout", label: t("term.cashout") }, { id: "cashin", label: t("term.cashin") }]} />
      </div>
      <div className="neu-scroll flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label={t("fc.why.day")}>
        {fc.days.map((d, i) => (
          <button key={d.date} role="tab" aria-selected={i === day} onClick={() => setDay(i)}
            className={cx("min-h-11 shrink-0 rounded-xl px-3 text-xs font-semibold", i === day ? "neu-inset text-accent" : "neu-raised-sm")}>
            {fmt.date(d.date)}{!d.is_working_day ? " ·" : ""}
          </button>
        ))}
      </div>
      <p className="text-sm font-semibold">{t("fc.why.baseline", { n: fmt.num(base) })}</p>
      <ol className="flex flex-col gap-2">
        {items.map((it, i) => {
          const label = feature(it);
          const up = it.bdt >= 0;
          return (
            <li key={i} className="neu-flat flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">{label}: <span className="text-accent">{it.flag ? t(it.flag === "yes" ? "common.yes" : "common.no") : it.value}</span></div>
                <div className="text-xs text-muted">{whySentence(it, t, fmt, label)}</div>
              </div>
              <span className={cx("neu-inset-sm tabular inline-flex items-center gap-1 px-2.5 py-1 text-sm font-bold", up ? "text-ok" : "text-high")}>
                {up ? <ArrowUpRight size={15} aria-hidden /> : <ArrowDownRight size={15} aria-hidden />}
                {fmt.signed(it.bdt)} <span className="text-xs font-semibold">{up ? t("fc.why.up") : t("fc.why.down")}</span>
              </span>
            </li>
          );
        })}
      </ol>
      <p className="text-xs text-muted">{t("fc.why.note")}</p>
    </NeuCard>
  );
}

/* --------------------------------------------------------------- events */
export function EventBanner({ fc }: { fc: Forecast }) {
  const { t, fmt } = useI18n();
  if (!fc.events.length) return null;
  return (
    <div className="flex flex-col gap-2">
      {fc.events.map((e) => (
        <p key={e.id} role="status" className="neu-inset flex items-start gap-2 p-3 text-sm font-medium text-watch">
          <TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
          {t("fc.manual.banner", { kind: t(`events.kind.${e.kind}` as "events.kind.fair"), mult: e.multiplier, start: fmt.dateTiny(e.start_date), end: fmt.dateTiny(e.end_date) })}
        </p>
      ))}
    </div>
  );
}

export { StatusBadge };
