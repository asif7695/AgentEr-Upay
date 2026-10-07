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

export type DepMode = "t_copula" | "correlated" | "ar1" | "independent";
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
  thresholds: { high: number; watch: number; adapted?: boolean };
  adaptive?: { mode: AdaMode; overrides: Partial<Record<AdaParam, number>> };
  model: { choice: "challenger" | "reference"; calibrated: boolean; name: string | null };
  dependence: { mode: DepMode; available: boolean; risk_independent: DepRisk | null; risk_correlated: DepRisk | null; note: string };
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
    recon_tolerance: number; manual_report_agents: string[]; dependence_mode: DepMode; model_choice: "challenger" | "reference";
    coverage_by_tier: Record<string, number>; buffer_by_tier: Record<string, number>; topup_mult_by_tier: Record<string, number>;
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

export interface FlowMetrics { n: number; wape: number; pinball: number; coverage80: number; coverage50: number; width80: number }
export type FamilyMetrics = { co: FlowMetrics; ci: FlowMetrics };
export interface PathRates { rates: Record<string, number | null>; n_windows: number; tail_error: number; coverage_error: number }
export interface ModelEvidence {
  stamp: string; generated: string;
  split: { train_target_end: string; val: string; calibration: string; test: string };
  rows: { train: number; val: number; cal: number; test: number };
  protocol: { labels: string; metrics: string; caveat: string };
  families: Record<string, FamilyMetrics>;
  unseen_agents: Record<string, FamilyMetrics>;
  unseen_event: Record<string, FamilyMetrics>;
  conformal: Record<"co" | "ci", Record<string, Record<string, number>>>;
  dependence: { n_origins?: number; t_nu?: number; ar1?: { rho_day: number; rho_cross: number }; method?: string; dataset?: string };
  paths?: { protocol: string; estimate: { n_origins: number; rho_day: number; rho_cross: number; t_nu: number }; results: Record<string, { "3d": PathRates; "7d": PathRates }> };
  active: { model_choice: "challenger" | "reference"; dependence_mode: DepMode };
}

export type AdaMode = "off" | "suggest" | "auto";
export interface AdaProfile {
  agent_id: string; tier: string; as_of: string; history_days: number; n_days: number; n_obs: number; breaches: number; breach_rate: number | null; z: number | null;
  hit80: number | null; bias_pct: number | null; vol: number | null; trend_pct: number | null; stockout_days_60: number; alert_n: number; alert_hits: number;
  precision: number | null; report_reliability: number | null;
}
export interface AdaReason { code: string; params: Record<string, number>; text: string }
export type AdaParam = "coverage_prob" | "buffer_frac" | "high_threshold" | "watch_threshold";
export interface AdaChange {
  id: number; agent_id: string; created_date: string; params: Partial<Record<AdaParam, { from: number; to: number; prev: number | null; new: number | null }>>;
  reasons: AdaReason[]; profile: AdaProfile; status: "proposed" | "applied" | "dismissed" | "reverted" | "superseded"; mode: "suggest" | "auto";
  decided_by: string | null; decided_at: string | null; created_at: string;
}
export interface AdaptiveView {
  date: string; mode: AdaMode; note: string; pending: number; active: number;
  guard: { min_days: number; z_gate: number; cov_up: number; cov_down: number; buf_floor: number; buf_cap: number; thr_shift: number; min_gap: number; min_alerts: number; cooldown_days: number };
  network: { precision: number; alerts: number; vol_all: number | null };
  agents: { agent_id: string; division: string; tier: string; profile: AdaProfile; base: Record<AdaParam, number>; active: Partial<Record<AdaParam, number>>; evidence_supports: Partial<Record<AdaParam, number>>; reasons: AdaReason[] }[];
  changes: AdaChange[];
}

export interface DetectedEventRow {
  id: number; scope: "agent" | "division"; target: string; flow: "both" | "cashout" | "cashin"; kind: "jump" | "shift"; direction: "up" | "down"; multiplier: number;
  start_date: string; end_date: string; status: "proposed" | "accepted" | "dismissed" | "expired" | "revoked"; event_id: number | null; created_date: string;
  decided_by: string | null; decided_at: string | null;
  evidence: { members: { agent_id: string; flow: string; kind: string; days: number; z_last: number; cusum: number; raw_ratio: number; multiplier: number }[]; protocol: string };
}
export interface DetectionEvidence {
  stamp: string; protocol: { rule: string };
  false_alarms: { nights: number; agent_nights: number; detections: number; detection_rate_per_agent_night: number; distinct_proposals: number; proposals_per_week: number; period: [string, string] };
  power: Record<string, { trials: number; detected: number; detection_rate: number; median_delay_days: number | null; within_3_days: number }>;
}

export interface TierCost { orders: number; unserved: number; demand: number; stockout_days: number; service_rate: number; trips_cost: number; lost_cost: number; lost_agent: number; lost_upay: number; capital_cost: number; total: number }
export interface PolicyNet extends TierCost { net_benefit: number }
export interface EconTier {
  agents: number; habit: TierCost; hybrid95: TierCost; model_only95: TierCost;
  optimum: TierCost & { coverage: number; buffer: number; up: number };
  net_benefit_95: number; net_benefit_optimum: number; roi_95: number | null; breakeven_trip_cost: number | null; breakeven_multiplier: number | null;
  curve: { coverage: number; cost_default: number; cost_best: number; orders: number; unserved: number; service_rate: number }[];
}
export interface EconomicsView {
  available: boolean; stamp: string; note: string; verdict: "model_guided_pays" | "habit_is_cheaper";
  assumptions: { trip_cost: Record<string, number>; margin_rate: number; agent_share: number; customer_multiplier: number; capital_cost_annual: number };
  defaults: { trip_cost: Record<string, number>; margin_rate: number; agent_share: number; customer_multiplier: number; capital_cost_annual: number };
  bounds: { trip_cost: [number, number]; margin_rate: [number, number]; agent_share: [number, number]; customer_multiplier: [number, number]; capital_cost_annual: [number, number] };
  tiers: Record<string, EconTier>;
  policies: Record<"habit" | "hybrid95" | "optimum" | "model_only95", PolicyNet>;
  sensitivity: { trip_scale: number; multiplier: number; coverage: number; buffer: number; up: number; net_benefit: number; beats_habit: boolean }[];
  optimum_params: Record<string, { coverage: number; buffer: number; up: number }>;
  applied: Record<string, { coverage: number; buffer: number; up: number }>;
}
