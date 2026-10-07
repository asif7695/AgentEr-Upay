"""Business rules. Deliberately separate from the ML model (rulebook: rules != model).

Everything here is deterministic and documented; every number in the UI traces either to a model quantile
(ml/serving.py) or to one of these rules.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, timedelta

import numpy as np

from . import allocation_rules, economics

_OPT = economics.optimum_params(economics.DEFAULT_ECONOMICS) or {}      # cost-optimal per-tier settings under the default assumptions

DEFAULT_RULES = dict(
    buffer_frac=0.10,            # "effectively out" = below 10% of capacity (risk_config.buffer_frac)
    coverage_prob=0.95,          # recommended level protects the window with this probability
    min_order_frac=0.10,         # ignore top-ups smaller than this share of capacity
    high_threshold=50.0,         # risk >= 50%  -> HIGH
    watch_threshold=30.0,        # 30-50%       -> WATCH ; below -> OK
    recon_tolerance=0.10,        # |gap| > 10% of ledger cash -> "needs verification"
    model_choice="challenger",     # "challenger" (our retrained + calibrated model) | "reference" (the supplied bundle)
    dependence_mode="t_copula",    # multi-day path dependence in the Monte Carlo: "t_copula" | "correlated" (Gaussian) | "ar1" | "independent" (supplied default)
    # Per agent tier (location type). Empty = fall back to the global value above. Defaults are the COST-OPTIMAL values from the ROI
    # replay under the placeholder economics below (see /admin/economics); the admin can change or re-optimise them.
    coverage_by_tier={t: v["coverage"] for t, v in _OPT.items()},
    buffer_by_tier={t: v["buffer"] for t, v in _OPT.items()},
    topup_mult_by_tier={t: v["up"] for t, v in _OPT.items()},     # order up to this multiple of the required level (fewer, larger trips)
    economics=economics.DEFAULT_ECONOMICS,
    allocation=allocation_rules.DEFAULT_ALLOCATION,   # distributor budgets for the network-wide allocation (placeholders, editable on the Dispatch page)
    adaptive_mode="suggest",       # per-agent adaptation of coverage / buffer / alert thresholds: "off" | "suggest" (admin approves) | "auto" (within guard rails)
    agent_overrides={},            # {agent_id: {coverage_prob?, buffer_frac?, high_threshold?, watch_threshold?}} written only by approved adaptive changes
    manual_report_agents=["A01"],  # agents whose replay report for 'today' stays pending (live-demo of the report form)
)

RULE_BOUNDS = dict(
    buffer_frac=(0.0, 0.5), coverage_prob=(0.5, 0.999), min_order_frac=(0.0, 0.5),
    high_threshold=(1.0, 100.0), watch_threshold=(0.0, 99.0), recon_tolerance=(0.01, 0.5),
)

DEPENDENCE_MODES = ("t_copula", "correlated", "ar1", "independent")
TOPUP_MULT_BOUNDS = (1.0, 3.0)
MODEL_CHOICES = ("challenger", "reference")
ADAPTIVE_MODES = ("off", "suggest", "auto")
OVERRIDE_BOUNDS = dict(coverage_prob=RULE_BOUNDS["coverage_prob"], buffer_frac=RULE_BOUNDS["buffer_frac"], high_threshold=(1.0, 100.0), watch_threshold=(0.0, 99.0))


# ---------------------------------------------------------------- status bands --
def status_from_risk(risk_pct: float, high: float, watch: float) -> str:
    if risk_pct >= high:
        return "HIGH"
    if risk_pct >= watch:
        return "WATCH"
    return "OK"


STATUS_RANK = {"OK": 0, "WATCH": 1, "HIGH": 2}


def worst_status(*s: str) -> str:
    return max(s, key=lambda x: STATUS_RANK[x])


def validate_rules(patch: dict, current: dict) -> dict:
    """Returns the merged rule dict or raises ValueError with a readable message."""
    merged = {**current, **patch}
    for k, (lo, hi) in RULE_BOUNDS.items():
        v = merged[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not (lo <= v <= hi):
            raise ValueError(f"{k} must be a number between {lo} and {hi}")
    if merged["watch_threshold"] >= merged["high_threshold"]:
        raise ValueError("watch_threshold must be below high_threshold")
    if merged["model_choice"] not in MODEL_CHOICES:
        raise ValueError("model_choice must be 'challenger' or 'reference'")
    if merged["dependence_mode"] not in DEPENDENCE_MODES:
        raise ValueError("dependence_mode must be one of t_copula, correlated, ar1, independent")
    for key, (lo, hi) in (("coverage_by_tier", RULE_BOUNDS["coverage_prob"]), ("buffer_by_tier", RULE_BOUNDS["buffer_frac"]), ("topup_mult_by_tier", TOPUP_MULT_BOUNDS)):
        m_ = merged[key]
        if not isinstance(m_, dict) or not set(m_) <= set(economics.TIERS):
            raise ValueError(f"{key} must map agent tiers ({', '.join(economics.TIERS)}) to numbers")
        for t, v in m_.items():
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not (lo <= v <= hi):
                raise ValueError(f"{key}[{t}] must be a number between {lo} and {hi}")
    if merged["adaptive_mode"] not in ADAPTIVE_MODES:
        raise ValueError("adaptive_mode must be one of off, suggest, auto")
    ov = merged["agent_overrides"]
    if not isinstance(ov, dict):
        raise ValueError("agent_overrides must map agent ids to settings")
    for aid, vals in ov.items():
        if not isinstance(vals, dict) or not set(vals) <= set(OVERRIDE_BOUNDS):
            raise ValueError(f"agent_overrides[{aid}] may only set {', '.join(OVERRIDE_BOUNDS)}")
        for k, v in vals.items():
            lo, hi = OVERRIDE_BOUNDS[k]
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not (lo <= v <= hi):
                raise ValueError(f"agent_overrides[{aid}].{k} must be a number between {lo} and {hi}")
    merged["allocation"] = allocation_rules.validate_allocation({}, merged["allocation"])
    merged["economics"] = economics.validate_economics({}, merged["economics"])
    m = merged["manual_report_agents"]
    if not isinstance(m, list) or not all(isinstance(x, str) and len(x) <= 8 for x in m):
        raise ValueError("manual_report_agents must be a list of agent ids")
    merged["manual_report_agents"] = sorted({x.upper() for x in m})
    return merged


def risk_cfg_overrides(rules: dict, tier: str | None = None, agent_id: str | None = None) -> dict:
    """The subset of rules that feed lf.risk_summary (merged onto a COPY of bundle['risk_config']).
    Precedence: an approved per-agent adaptation > the per-tier value > the global value."""
    ov = rules.get("agent_overrides", {}).get(agent_id, {}) if agent_id else {}
    return dict(buffer_frac=float(ov.get("buffer_frac", rules.get("buffer_by_tier", {}).get(tier, rules["buffer_frac"]))),
                coverage_prob=float(ov.get("coverage_prob", rules.get("coverage_by_tier", {}).get(tier, rules["coverage_prob"]))),
                min_order_frac=float(rules["min_order_frac"]))


def thresholds(rules: dict, agent_id: str | None = None) -> tuple[float, float]:
    """(high, watch) alert thresholds for an agent: an approved per-agent adaptation wins over the global rule."""
    ov = rules.get("agent_overrides", {}).get(agent_id, {}) if agent_id else {}
    return float(ov.get("high_threshold", rules["high_threshold"])), float(ov.get("watch_threshold", rules["watch_threshold"]))


def topup_mult(rules: dict, tier: str | None) -> float:
    return float(rules.get("topup_mult_by_tier", {}).get(tier, 1.0))


def topup_amount(req_level: float, current: float, cap: float, mult: float, min_order_frac: float) -> float:
    """Order up to mult x the required level (never above capacity); ignore orders smaller than min_order_frac of capacity."""
    target = min(cap, mult * req_level) if mult > 1.0 else req_level
    need = max(0.0, target - current)
    return need if need >= min_order_frac * cap else 0.0


def config_hash(rules: dict, tier: str | None = None, agent_id: str | None = None) -> str:
    return hashlib.sha1(json.dumps({**risk_cfg_overrides(rules, tier, agent_id), "dep": rules["dependence_mode"], "model": rules["model_choice"]}, sort_keys=True).encode()).hexdigest()[:10]


# ------------------------------------------------------------- reconciliation --
def reconcile(ledger_cash: float, reported_cash: float | None, tolerance: float = 0.10, pending: bool = False) -> dict:
    """Ledger vs self-report. gap% = (reported - ledger) / ledger.

    * no report (missing or still pending today) -> use ledger estimate, "Estimated, not confirmed today"
    * |gap| > tolerance                         -> flag "needs verification", forecast uses the LEDGER value
    * otherwise                                  -> the agent's count is used
    Copy is neutral by design: a gap is a prompt to verify, never an accusation.
    """
    if reported_cash is None or (isinstance(reported_cash, float) and math.isnan(reported_cash)):
        return dict(status="pending" if pending else "missing", reported_cash=None, ledger_cash=ledger_cash, gap=None,
                    gap_pct=None, cash_used=ledger_cash, cash_source="ledger_estimate", flagged=False,
                    label="Estimated, not confirmed today")
    gap = reported_cash - ledger_cash
    if ledger_cash <= 0:
        gap_pct = 0.0 if reported_cash == 0 else None
        flagged = reported_cash != 0
    else:
        gap_pct = gap / ledger_cash
        flagged = abs(gap_pct) > tolerance + 1e-12
    if flagged:
        return dict(status="needs_verification", reported_cash=reported_cash, ledger_cash=ledger_cash, gap=gap,
                    gap_pct=gap_pct, cash_used=ledger_cash, cash_source="ledger_estimate", flagged=True,
                    label="Needs verification")
    return dict(status="confirmed", reported_cash=reported_cash, ledger_cash=ledger_cash, gap=gap, gap_pct=gap_pct,
                cash_used=reported_cash, cash_source="reported", flagged=False, label="Confirmed")


# ------------------------------------------------------------ human overrides --
def event_multipliers(events: list[dict], agent: dict, target_dates: list[date]) -> np.ndarray:
    """(H, 2) multipliers [cash-out, cash-in] from active human events. Multiple events multiply.
    This is a MANUAL ADJUSTMENT, not learned by the model."""
    m = np.ones((len(target_dates), 2))
    for ev in events:
        if not ev.get("active", True):
            continue
        scope = ev["scope"]
        if scope == "agent" and ev["target"] != agent["agent_id"]:
            continue
        if scope == "division" and ev["target"] != agent["division"]:
            continue
        a, b = date.fromisoformat(ev["start_date"]), date.fromisoformat(ev["end_date"])
        for i, d in enumerate(target_dates):
            if a <= d <= b:
                if ev["flow"] in ("both", "cashout"):
                    m[i, 0] *= ev["multiplier"]
                if ev["flow"] in ("both", "cashin"):
                    m[i, 1] *= ev["multiplier"]
    return m


def active_events_for(events: list[dict], agent: dict, target_dates: list[date]) -> list[dict]:
    out = []
    for ev in events:
        if not ev.get("active", True):
            continue
        if ev["scope"] == "agent" and ev["target"] != agent["agent_id"]:
            continue
        if ev["scope"] == "division" and ev["target"] != agent["division"]:
            continue
        a, b = date.fromisoformat(ev["start_date"]), date.fromisoformat(ev["end_date"])
        if any(a <= d <= b for d in target_dates):
            out.append(ev)
    return out


# ------------------------------------------------------------ top-up planning --
def next_working_day(origin: date, working: dict[date, bool]) -> date:
    d = origin + timedelta(days=1)
    while not working.get(d, d.weekday() not in (4, 5)):
        d += timedelta(days=1)
    return d


def topup_by_date(origin: date, likely_runout_day: int | None, working: dict[date, bool]) -> dict:
    """Latest working day strictly before the likely run-out date (a top-up must land before the balance is gone),
    but never earlier than the next working day (distributor offices only act on working days).
    `late` = the next possible working day is already on/after the likely run-out date."""
    nxt = next_working_day(origin, working)
    if likely_runout_day is None:
        return dict(by_date=nxt, late=False, runout_date=None, next_working_day=nxt)
    runout = origin + timedelta(days=likely_runout_day)
    cands = [origin + timedelta(days=k) for k in range(1, likely_runout_day)
             if working.get(origin + timedelta(days=k), False)]
    if cands:
        return dict(by_date=cands[-1], late=False, runout_date=runout, next_working_day=nxt)
    return dict(by_date=nxt, late=nxt >= runout, runout_date=runout, next_working_day=nxt)


def capital_gap(req_cash: float, req_ef: float, cash: float, ef: float) -> float:
    """Extra capital needed when the total float cannot cover the coming window."""
    return max(0.0, req_cash + req_ef - cash - ef)


def order_type(status: str, by: dict) -> str:
    """Emergency = HIGH risk and the next possible top-up lands on/after the likely run-out date."""
    return "emergency" if status == "HIGH" and by["late"] else "planned"


def rank_key(row: dict):
    """Risk ranking: worst headline risk first, then capital need, then agent id (stable)."""
    return (-max(row["cash_risk_pct"], row["efloat_risk_pct"]), not row["float_insufficient"], row["agent_id"])
