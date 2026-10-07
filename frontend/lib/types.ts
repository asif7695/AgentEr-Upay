export type Status = "HIGH" | "WATCH" | "OK";
export type Role = "admin" | "agent";

export interface User { username: string; role: Role; agent_id: string | null; display_name: string }

export interface SimState {
  date: string; weekday: string; min_date: string; max_date: string; reveal_max_date: string;
  can_advance: boolean; can_reveal: boolean; synthetic_data: boolean;
}

export interface Reconciliation {
  status: "confirmed" | "needs_verification" | "missing" | "pending";
  reported_cash: number | null; ledger_cash: number; gap: number | null; gap_pct: number | null;
  cash_used: number; cash_source: "reported" | "ledger_estimate"; flagged: boolean; label: string;
  date: string; source: string | null; submitted_at: string | null;
}

export interface Section {
  risk_pct: number; risk_pct_7d: number; risk_by_day: number[]; status: Status;
  window_days: number; window_end_date: string;
  likely_runout_day: number | null; likely_runout_date: string | null;
  current: number; capacity: number; buffer: number; pct_of_capacity: number;
  recommended_level: number; gap_vs_current: number;
  topup: number; topup_by_date: string | null; topup_late: boolean; next_working_day: string;
  source: Record<string, string>;
}

export interface Dist { p10: number; p25: number; p50: number; p75: number; p90: number; mean: number; expected: number; p_surge: number }
export interface DayFc {
  k: number; date: string; dow: string; is_working_day: boolean; is_holiday: boolean;
  cashout: Dist; cashin: Dist; manual_multiplier: { cashout: number; cashin: number };
}
export interface Bands { p10: number[]; p50: number[]; p90: number[] }
export interface WhyItem { feature: string | null; label: string; value: string; flag: "yes" | "no" | null; bdt: number; text: string }
export interface Why {
  cashout: WhyItem[][]; cashin: WhyItem[][]; baseline_cashout: number[]; baseline_cashin: number[]; note: string;
}
export type Action =
  | { type: "cash_topup" | "efloat_topup"; kind: "cash" | "efloat"; amount: number; by_date: string; late: boolean; order_type: "planned" | "emergency" }
  | { type: "capital"; amount: number }
  | { type: "submit_report" }
  | { type: "verify_report"; gap_pct: number | null }
  | { type: "all_good" };

export interface DepRisk { cash: number; efloat: number; cash_7d: number; efloat_7d: number }
export interface Forecast {
  agent: { agent_id: string; division: string; location_type: string; capacity_cash: number; capacity_efloat: number };
  as_of: string; sim_date: string; status: Status;
  balances: { cash: { value: number; ledger: number; reported: number | null; source: string }; efloat: { value: number; ledger: number; source: string } };
  reconciliation: Reconciliation;
  cash: Section; efloat: Section;
  capital: { insufficient: boolean; needed: number; total_float: number; required_cash: number; required_efloat: number };
  days: DayFc[];
  bands: { dates: string[]; cash: Bands; efloat: Bands; buffer_cash: number; buffer_efloat: number; capacity_cash: number; capacity_efloat: number };
  actions: Action[];
  expected_unserved: { cash: number; efloat: number; total: number; note: string };
  events: { id: number; kind: string; multiplier: number; flow: string; start_date: string; end_date: string; note: string | null; label: string }[];
  thresholds: { high: number; watch: number };
  dependence: { mode: "correlated" | "independent"; available: boolean; risk_independent: DepRisk | null; risk_correlated: DepRisk | null; note: string };
  config: { buffer_frac: number; coverage_prob: number; min_order_frac: number; n_paths: number; surge_multiple: number };
  why?: Why;
  synthetic_data: boolean;
}

export interface AgentRow {
  rank: number; agent_id: string; division: string; location_type: string; status: Status;
  cash_risk_pct: number; efloat_risk_pct: number; cash_status: Status; efloat_status: Status; window_days: number;
  likely_cash_runout_date: string | null; likely_efloat_runout_date: string | null;
  cash_pct_of_capacity: number; efloat_pct_of_capacity: number; cash_balance: number; efloat_balance: number;
  topup_cash: number; topup_efloat: number; topup_cash_by: string | null; topup_efloat_by: string | null; topup_late: boolean;
  float_insufficient: boolean; capital_needed: number; expected_unserved: number;
  report_status: Reconciliation["status"]; report_label: string; gap_pct: number | null; has_event: boolean;
}
export interface Overview {
  date: string;
  kpis: {
    high: number; watch: number; ok: number; expected_unserved: number; planned_topup_cash: number; planned_topup_efloat: number;
    planned_topup_total: number; agents_needing_capital: number; reports_missing: number; reports_flagged: number; open_alerts: number;
  };
  agents: AgentRow[];
  divisions: { division: string; agents: number; high: number; watch: number; ok: number; topup_total: number; worst: Status; agent_ids: string[] }[];
  thresholds: { high: number; watch: number }; note: string;
}

export interface Order {
  id: number; agent_id: string; plan_date: string; due_date: string; kind: "cash" | "efloat"; amount: number;
  order_type: "planned" | "emergency"; status: "proposed" | "acknowledged" | "scheduled" | "done" | "cancelled";
  scheduled_for: string | null; note: string | null; created_by: string; created_at: string; updated_at: string; meaning: string;
}
export interface DispatchItem {
  agent_id: string; division: string; location_type: string; kind: "cash" | "efloat"; meaning: string; amount: number;
  by_date: string; urgent: boolean; order_type: "planned" | "emergency"; status: Status; risk_pct: number;
  likely_runout_date: string | null; float_insufficient: boolean; capital_needed: number; order: Order | null;
}
export interface DispatchPlan {
  date: string; next_working_day: string; note: string;
  divisions: { division: string; items: DispatchItem[]; total_cash: number; total_efloat: number; needs_capital: string[] }[];
  totals: { cash: number; efloat: number; orders: number; emergency: number };
}

export interface HistoryRow {
  date: string; closing_cash: number; closing_efloat: number; cash_topup: number; efloat_topup: number;
  cash_stockout: boolean; efloat_stockout: boolean; cashout: number; cashin: number;
  report: { status: Reconciliation["status"]; label: string; reported_cash: number | null; gap: number | null; gap_pct: number | null };
}
export interface History {
  agent_id: string; capacity_cash: number; capacity_efloat: number; rows: HistoryRow[];
  totals: { cash_stockout_days: number; efloat_stockout_days: number; cash_topups: number; efloat_topups: number };
}

export interface AlertItem {
  id: number; agent_id: string; date: string; type: string; severity: "high" | "watch" | "info"; message: string;
  params: Record<string, number | null>; status: "open" | "acked"; created_at: string; acked_by: string | null; acked_at: string | null;
}

export interface RulesView {
  rules: {
    buffer_frac: number; coverage_prob: number; min_order_frac: number; high_threshold: number; watch_threshold: number;
    recon_tolerance: number; manual_report_agents: string[]; dependence_mode: "correlated" | "independent";
  };
  config_hash: string; bounds: Record<string, [number, number]>; defaults: Record<string, unknown>;
  model_risk_config: Record<string, number>; note: string;
}
export interface EventItem {
  id: number; scope: "all" | "division" | "agent"; target: string | null; kind: string; flow: "both" | "cashout" | "cashin";
  multiplier: number; start_date: string; end_date: string; note: string | null; active: boolean; created_by: string; label: string;
}
export interface AuditItem { id: number; ts: string; actor: string; action: string; entity: string; entity_id: string | null; detail: Record<string, unknown> }

export interface RevealDay {
  k: number; date: string; true_cashout: number; true_cashin: number; served_cashout: number; served_cashin: number;
  unserved_cashout: number; unserved_cashin: number; closing_cash: number; closing_efloat: number; cash_topup: number; efloat_topup: number;
  cash_stockout: boolean; efloat_stockout: boolean; no_topup_cash: number; no_topup_efloat: number;
}
export interface Reveal {
  agent_id: string; origin: string; label: string; days: RevealDay[];
  summary: { cash_stockout_days: number; efloat_stockout_days: number; unserved_total: number; counterfactual_cash_breach: boolean; counterfactual_efloat_breach: boolean; counterfactual_note: string };
}

export interface Impact {
  label: string; source: string;
  policy_replay: {
    period: string; agents: number; days: number;
    policies: { key: "habit" | "hybrid" | "model_only"; name: string; rule: string; stockout_days: number; cash_stockout_days: number | null; efloat_stockout_days: number | null; unserved_bdt: number; orders: number }[];
    deltas: Record<string, { stockout_days_pct: number; unserved_pct: number; orders_pct: number }>;
  };
  coverage_sweep: { coverage: number; stockout_days: number; orders: number }[];
  coverage_habit: { stockout_days: number; orders: number };
  reduction_by_type: { type: string; reduction_pct: number }[];
  garment_capital: { pct_days_requirement_exceeds_total_float: number; avg_shortfall_bdt: number };
  accuracy: {
    period: string; wape_cashout: number; wape_cashin: number; baseline_cashout: number; baseline_cashin: number; noise_floor: number;
    interval80_coverage_cashout: number; interval80_coverage_cashin: number;
    unseen_agent: { cashout_unseen: number; cashout_seen: number }; unseen_festival: { cashout: number; cashin: number; note: string };
  };
  limitations: string[];
}

export interface ApiErrorBody { error: { code: string; message: string; details?: unknown } }
export interface PipelineStep { date: string; ledger_rows_ingested: number; reports_requested: number; forecasts_recomputed: number; alerts_created: number; elapsed_ms: number }
