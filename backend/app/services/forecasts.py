"""Forecast service: cache + the JSON payload carrying the five outputs for one agent on one date.

Cache key = (agent, date, config hash, cash input, event-multiplier hash). Status/threshold logic is applied
AFTER the cache, so changing alert thresholds never needs a re-simulation.
"""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from datetime import date, timedelta

import numpy as np

from .. import settings
from ..errors import ApiError
from ..ml import liquidity_forecaster as lf
from ..ml import serving
from ..ml.dependence import load_dependence
from ..ml.model_store import effective_model, get_bundle
from ..rules import business_rules as br
from .context import Ctx, ledger

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_cache: "OrderedDict[tuple, dict]" = OrderedDict()
_expl_cache: "OrderedDict[tuple, dict]" = OrderedDict()
_lock = threading.Lock()
STATS = {"hits": 0, "misses": 0}


def _lru_get(c, key):
    with _lock:
        if key in c:
            c.move_to_end(key)
            return c[key]
    return None


def _lru_put(c, key, val):
    with _lock:
        c[key] = val
        c.move_to_end(key)
        while len(c) > settings.FORECAST_CACHE_SIZE:
            c.popitem(last=False)


def seed_for(agent_id: str, d: date) -> int:
    return int(agent_id[1:]) * 1_000_003 + d.toordinal()


def _r(x, n=0):
    return round(float(x), n)


def _calendar(d: date) -> dict:
    cal = lf.build_calendar([d + timedelta(days=k) for k in range(0, 22)], get_bundle()["calendar_config"])
    return {r.date.date(): dict(working=bool(r.is_working_day), holiday=bool(r.is_holiday)) for r in cal.itertuples()}


def raw_forecast(ctx: Ctx, agent_id: str, d: date, cash_used: float, efloat: float,
                 mode: str | None = None) -> tuple[dict, np.ndarray]:
    """mode: one of br.DEPENDENCE_MODES (default: the admin rule). Falls back to independent if no estimate is available."""
    agent = ctx.agent(agent_id)
    mode = mode or ctx.rules["dependence_mode"]
    dep = load_dependence(mode, agent["location_type"])
    mode = mode if dep is not None else "independent"
    model = effective_model(ctx.rules["model_choice"])
    targets = [d + timedelta(days=k) for k in range(1, lf.H + 1)]
    mult = br.event_multipliers(ctx.events, agent, targets)
    key = (agent_id, d.isoformat(), br.config_hash({**ctx.rules, "dependence_mode": mode, "model_choice": model}, agent["location_type"], agent_id), int(round(cash_used)), hashlib.sha1(mult.tobytes()).hexdigest()[:8])
    hit = _lru_get(_cache, key)
    if hit is not None:
        STATS["hits"] += 1
        return hit, mult
    STATS["misses"] += 1
    bundle = get_bundle(model)
    hist = ledger.history(agent_id, d)
    if len(hist) < lf.MIN_HIST:
        raise ApiError(422, "insufficient_history", "Need at least 28 days of history")
    cfg = {**bundle["risk_config"], **br.risk_cfg_overrides(ctx.rules, agent["location_type"], agent_id)}       # copy: the pickle is never mutated
    out = serving.run_forecast(bundle, hist, serving.agent_row_for_serving(bundle, agent_id), d, cash_used, efloat,
                               cfg, mult, seed_for(agent_id, d), dependence=dep, location_type=agent["location_type"])
    out["dependence_mode"], out["model"] = mode, model
    _lru_put(_cache, key, out)
    return out, mult


def _section(kind, raw, d, rules, working, current, cap, buf, risk_by_day, risk_7d, runout, req_level, topup, cov=None, mult=1.0, thr=None):
    W = int(raw["coverage_window_days"])
    headline = float(risk_by_day[W - 1])
    by = br.topup_by_date(d, runout, working)
    high, watch = thr if thr is not None else (rules["high_threshold"], rules["watch_threshold"])
    status = br.status_from_risk(headline, high, watch)
    return dict(
        risk_pct=_r(headline, 1), risk_pct_7d=_r(risk_7d, 1), risk_by_day=[_r(x, 1) for x in risk_by_day], status=status,
        window_days=W, window_end_date=(d + timedelta(days=W)).isoformat(),
        likely_runout_day=runout, likely_runout_date=by["runout_date"].isoformat() if by["runout_date"] else None,
        current=_r(current), capacity=_r(cap), buffer=_r(buf), pct_of_capacity=_r(100 * current / cap, 1),
        recommended_level=_r(req_level), gap_vs_current=_r(req_level - current),
        topup=_r(topup), topup_by_date=by["by_date"].isoformat() if topup > 0 else None, topup_late=bool(by["late"] and topup > 0),
        next_working_day=by["next_working_day"].isoformat(),
        source={"risk_pct": "model_quantile+monte_carlo", "recommended_level": f"rule:coverage_prob={cov if cov is not None else rules['coverage_prob']}",
                "topup": f"rule:min_order_frac={rules['min_order_frac']},order_up_to_x{mult}"},
    ), by


def _dep_risk(r: dict | None, W: int) -> dict | None:
    if r is None:
        return None
    return dict(cash=_r(r["cash_risk_pct_by_day"][W - 1], 1), efloat=_r(r["efloat_risk_pct_by_day"][W - 1], 1),
                cash_7d=_r(r["cash_risk_pct_7d"], 1), efloat_7d=_r(r["efloat_risk_pct_7d"], 1))


def get_forecast(ctx: Ctx, agent_id: str, d: date, explain: bool = False, compare: bool = False) -> dict:
    """compare=True also runs the other dependence mode (one extra MC run) for the independent-vs-correlated line."""
    agent_id = agent_id.upper()
    ctx.check_date(d)
    agent = ctx.agent(agent_id)
    led = ledger.row(agent_id, d)
    if led is None:
        raise ApiError(404, "not_found", f"No ledger data for {agent_id} on {d.isoformat()}")
    rec = ctx.reconciliation(agent_id, d)
    cash, ef = float(rec["cash_used"]), float(led["closing_efloat"])
    raw, mult = raw_forecast(ctx, agent_id, d, cash, ef)
    rules = ctx.rules
    cal = _calendar(d)
    working = {k: v["working"] for k, v in cal.items()}
    cap_c, cap_e = raw["cap_cash"], raw["cap_efloat"]

    tier = agent["location_type"]
    used = raw["risk_cfg_used"]
    up_mult = br.topup_mult(rules, tier)
    thr = br.thresholds(rules, agent_id)
    up_c = br.topup_amount(raw["recommended_cash_level"], cash, cap_c, up_mult, rules["min_order_frac"])
    up_e = br.topup_amount(raw["recommended_efloat_level"], ef, cap_e, up_mult, rules["min_order_frac"])
    cash_sec, by_c = _section("cash", raw, d, rules, working, cash, cap_c, raw["buffer_cash"], raw["cash_risk_pct_by_day"],
                              raw["cash_risk_pct_7d"], raw["likely_cash_runout_day"], raw["recommended_cash_level"],
                              up_c, used["coverage_prob"], up_mult, thr)
    ef_sec, by_e = _section("efloat", raw, d, rules, working, ef, cap_e, raw["buffer_efloat"], raw["efloat_risk_pct_by_day"],
                            raw["efloat_risk_pct_7d"], raw["likely_efloat_runout_day"], raw["recommended_efloat_level"],
                            up_e, used["coverage_prob"], up_mult, thr)
    status = br.worst_status(cash_sec["status"], ef_sec["status"])
    cap_needed = br.capital_gap(raw["recommended_cash_level"], raw["recommended_efloat_level"], cash, ef) if raw["float_insufficient"] else 0.0

    days = []
    for k in range(lf.H):
        td = d + timedelta(days=k + 1)
        qo, qi = raw["cashout_q"][k], raw["cashin_q"][k]
        days.append(dict(
            k=k + 1, date=td.isoformat(), dow=DOW[td.weekday()], is_working_day=cal[td]["working"], is_holiday=cal[td]["holiday"],
            cashout=dict(p10=_r(qo[0]), p25=_r(qo[1]), p50=_r(qo[2]), p75=_r(qo[3]), p90=_r(qo[4]),
                         mean=_r(raw["mean_cashout"][k]), expected=_r(raw["expected_cashout"][k]), p_surge=_r(raw["p_cashout_surge"][k], 3)),
            cashin=dict(p10=_r(qi[0]), p25=_r(qi[1]), p50=_r(qi[2]), p75=_r(qi[3]), p90=_r(qi[4]),
                        mean=_r(raw["mean_cashin"][k]), expected=_r(raw["expected_cashin"][k]), p_surge=_r(raw["p_cashin_surge"][k], 3)),
            manual_multiplier=dict(cashout=_r(mult[k, 0], 3), cashin=_r(mult[k, 1], 3)),
        ))

    band_dates = [(d + timedelta(days=k)).isoformat() for k in range(0, lf.H + 1)]
    mk = lambda cur, b: {p: [_r(cur)] + [_r(x) for x in b[p]] for p in ("p10", "p50", "p90")}
    bands = dict(dates=band_dates, cash=mk(cash, raw["bands"]["cash"]), efloat=mk(ef, raw["bands"]["efloat"]),
                 buffer_cash=_r(raw["buffer_cash"]), buffer_efloat=_r(raw["buffer_efloat"]),
                 capacity_cash=_r(cap_c), capacity_efloat=_r(cap_e))

    actions = []
    for sec, kind, by in ((cash_sec, "cash", by_c), (ef_sec, "efloat", by_e)):
        if sec["topup"] > 0:
            actions.append(dict(type=f"{kind}_topup", kind=kind, amount=sec["topup"], by_date=sec["topup_by_date"], late=sec["topup_late"],
                                order_type=br.order_type(status, dict(late=sec["topup_late"]))))
    if raw["float_insufficient"]:
        actions.append(dict(type="capital", amount=_r(cap_needed)))
    if rec["status"] in ("pending", "missing"):
        actions.append(dict(type="submit_report"))
    elif rec["status"] == "needs_verification":
        actions.append(dict(type="verify_report", gap_pct=_r(100 * rec["gap_pct"], 1) if rec["gap_pct"] is not None else None))
    if not actions:
        actions.append(dict(type="all_good"))

    unserved = raw["expected_unserved"]
    W0 = int(raw["coverage_window_days"])
    by_mode = {raw["dependence_mode"]: raw}
    if compare:
        alt, _ = raw_forecast(ctx, agent_id, d, cash, ef, "t_copula" if raw["dependence_mode"] == "independent" else "independent")
        by_mode[alt["dependence_mode"]] = alt
    dependence = dict(
        mode=raw["dependence_mode"], available=any(m != "independent" for m in by_mode),
        risk_independent=_dep_risk(by_mode.get("independent"), W0),
        risk_correlated=_dep_risk(next((v for m, v in by_mode.items() if m != "independent"), None), W0),
        note="Correlated mode lets a high-demand day raise the next days' demand (Gaussian copula on the model's residuals). "
             "The supplied risk engine is unchanged.")
    payload = dict(
        agent=dict(agent_id=agent_id, division=agent["division"], location_type=agent["location_type"],
                   capacity_cash=_r(cap_c), capacity_efloat=_r(cap_e)),
        as_of=d.isoformat(), sim_date=ctx.sim_date.isoformat(), status=status,
        balances=dict(cash=dict(value=_r(cash), ledger=_r(led["closing_cash"]), reported=rec["reported_cash"], source=rec["cash_source"]),
                      efloat=dict(value=_r(ef), ledger=_r(ef), source="ledger")),
        reconciliation=rec,
        cash=cash_sec, efloat=ef_sec,
        capital=dict(insufficient=bool(raw["float_insufficient"]), needed=_r(cap_needed), total_float=_r(cash + ef),
                     required_cash=_r(raw["recommended_cash_level"]), required_efloat=_r(raw["recommended_efloat_level"])),
        days=days, bands=bands, actions=actions, dependence=dependence,
        model=dict(choice=raw["model"], calibrated=bool(get_bundle(raw["model"]).get("calibration")), name=get_bundle(raw["model"]).get("name")),
        expected_unserved=dict(cash=_r(unserved["cash"]), efloat=_r(unserved["efloat"]), total=_r(unserved["cash"] + unserved["efloat"]),
                               note="Model estimate inside the coverage window (Monte Carlo); not ground truth."),
        events=[dict(id=e["id"], kind=e["kind"], multiplier=e["multiplier"], flow=e["flow"], start_date=e["start_date"], end_date=e["end_date"],
                     note=e["note"], label="manual adjustment, not learned by the model")
                for e in br.active_events_for(ctx.events, agent, [d + timedelta(days=k) for k in range(1, lf.H + 1)])],
        thresholds=dict(high=thr[0], watch=thr[1], adapted=agent_id in rules["agent_overrides"] and any(k in rules["agent_overrides"][agent_id] for k in ("high_threshold", "watch_threshold"))),
        adaptive=dict(mode=rules["adaptive_mode"], overrides=rules["agent_overrides"].get(agent_id, {})),
        config=dict(buffer_frac=used["buffer_frac"], coverage_prob=used["coverage_prob"], min_order_frac=rules["min_order_frac"], topup_mult=up_mult, tier=tier,
                    n_paths=raw["risk_cfg_used"]["n_paths"], surge_multiple=raw["risk_cfg_used"]["surge_multiple"]),
        quantile_levels=raw["quantile_levels"],
        synthetic_data=True,
    )
    if explain:
        payload["why"] = get_explanations(ctx, agent_id, d, cash, ef)
    return payload


def get_explanations(ctx: Ctx, agent_id: str, d: date, cash: float, ef: float) -> dict:
    model = effective_model(ctx.rules["model_choice"])
    key = (agent_id, d.isoformat(), model)
    hit = _lru_get(_expl_cache, key)
    if hit is None:
        bundle = get_bundle(model)
        hit = serving.explain_days(bundle, ledger.history(agent_id, d), serving.agent_row_for_serving(bundle, agent_id), d, cash, ef, top=5)
        hit = {k: ([[{**i, "bdt": _r(i["bdt"])} for i in day] for day in v] if k in ("cashout", "cashin") else [_r(x) for x in v])
               for k, v in hit.items()}
        hit["note"] = ("Drivers explain the model's median forecast only; manual event adjustments are not included. "
                       "A line like 'public holiday: no, +3,184' means: not a holiday, so demand is higher than the all-days average.")
        _lru_put(_expl_cache, key, hit)
    return hit


def summary(p: dict) -> dict:
    """Slim per-agent row used by overview / dispatch."""
    return dict(
        agent_id=p["agent"]["agent_id"], division=p["agent"]["division"], location_type=p["agent"]["location_type"], status=p["status"],
        cash_risk_pct=p["cash"]["risk_pct"], efloat_risk_pct=p["efloat"]["risk_pct"],
        cash_status=p["cash"]["status"], efloat_status=p["efloat"]["status"], window_days=p["cash"]["window_days"],
        likely_cash_runout_date=p["cash"]["likely_runout_date"], likely_efloat_runout_date=p["efloat"]["likely_runout_date"],
        cash_pct_of_capacity=p["cash"]["pct_of_capacity"], efloat_pct_of_capacity=p["efloat"]["pct_of_capacity"],
        cash_balance=p["cash"]["current"], efloat_balance=p["efloat"]["current"],
        topup_cash=p["cash"]["topup"], topup_efloat=p["efloat"]["topup"],
        topup_cash_by=p["cash"]["topup_by_date"], topup_efloat_by=p["efloat"]["topup_by_date"],
        topup_late=p["cash"]["topup_late"] or p["efloat"]["topup_late"],
        float_insufficient=p["capital"]["insufficient"], capital_needed=p["capital"]["needed"],
        expected_unserved=p["expected_unserved"]["total"], report_status=p["reconciliation"]["status"],
        report_label=p["reconciliation"]["label"], gap_pct=p["reconciliation"]["gap_pct"], has_event=bool(p["events"]),
    )
