"use client";
import { Bell, Check, Eye, Info, TriangleAlert } from "lucide-react";
import { NeuBadge, NeuButton, cx } from "@/components/neu";
import type { DictKey } from "@/lib/dict.en";
import { useI18n } from "@/lib/i18n";
import type { AlertItem } from "@/lib/types";

const SEV_ICON = { high: TriangleAlert, watch: Eye, info: Info } as const;
const SEV_TONE = { high: "high", watch: "watch", info: "neutral" } as const;

export function useAlertText() {
  const { t, fmt, lang } = useI18n();
  return (a: AlertItem) => {
    const p = a.params as Record<string, number | null>;
    const gp = p.gap_pct;
    const gap = gp == null ? "" : lang === "bn" ? ` (${fmt.signed(gp)}%)` : ` by ${fmt.signed(gp)}%`;
    const key = `alerts.msg.${a.type}` as DictKey;
    try {
      return t(key, { agent: a.agent_id, c: fmt.num(p.cash_pct ?? 0), e: fmt.num(p.efloat_pct ?? 0), w: fmt.num(p.window_days ?? 0), date: fmt.date(a.date), gap, amount: fmt.num(p.needed ?? 0), pct: fmt.num(Math.abs(p.pct ?? 0)) });
    } catch { return a.message; }
  };
}

export function AlertList({ alerts, onAck, showAgent = true }: { alerts: AlertItem[]; onAck?: (id: number) => void; showAgent?: boolean }) {
  const { t, fmt } = useI18n();
  const text = useAlertText();
  return (
    <ul className="flex flex-col gap-2">
      {alerts.map((a) => {
        const Icon = SEV_ICON[a.severity] ?? Bell;
        const key = `alerts.type.${a.type}` as DictKey;
        return (
          <li key={a.id} className={cx("neu-flat flex flex-wrap items-center justify-between gap-3 px-3 py-2.5", a.status === "acked" && "opacity-70")}>
            <div className="flex min-w-0 flex-1 basis-64 items-start gap-3">
              <span className={cx("pill grid h-9 w-9 shrink-0 place-items-center !rounded-xl", a.severity === "high" ? "pill-high text-high" : a.severity === "watch" ? "pill-watch text-watch" : "text-muted")}><Icon size={17} aria-hidden /></span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <NeuBadge tone={SEV_TONE[a.severity]}>{t(`alerts.sev.${a.severity}` as const)}</NeuBadge>
                  <span className="font-bold">{t(key)}</span>
                  {showAgent && <span className="text-muted">{a.agent_id}</span>}
                  <span className="text-muted">{fmt.dateTiny(a.date)}</span>
                </div>
                <p className="mt-1 text-sm">{text(a)}</p>
              </div>
            </div>
            {a.status === "open" && onAck
              ? <NeuButton onClick={() => onAck(a.id)} icon={<Check size={16} aria-hidden />}>{t("alerts.ack")}</NeuButton>
              : a.status === "acked" ? <NeuBadge tone="ok" icon={<Check size={13} aria-hidden />}>{t("alerts.acked")}</NeuBadge> : null}
          </li>
        );
      })}
    </ul>
  );
}
