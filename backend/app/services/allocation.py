"""Network-wide allocation service: gathers every agent's forecast distribution, solves the day's allocation, and (on approval)
turns the lines into ordinary planning orders. The solver itself is in rules/allocation_rules.py."""
from __future__ import annotations

import numpy as np
from datetime import date
from sqlalchemy import select

from ..errors import ApiError
from ..models import Order
from ..rules import allocation_rules as ar
from ..rules import business_rules as br
from .context import Ctx, audit, ledger
from .dispatch import KINDS, create_order, order_dict
from .forecasts import get_forecast, raw_forecast

BUDGET_POINTS = 9


def _economics(ctx: Ctx) -> tuple[dict, float, float]:
    e = ctx.rules["economics"]
    return e, e["margin_rate"] * e["customer_multiplier"], e["capital_cost_annual"] * ar.HORIZON_DAYS / 365.0


def gather(ctx: Ctx, d: date, settings: dict) -> tuple[list[ar.Candidate], dict[str, dict]]:
    e, v, lam = _economics(ctx)
    cands: list[ar.Candidate] = []
    fcs: dict[str, dict] = {}
    for aid in sorted(ledger.agents):
        p = get_forecast(ctx, aid, d)
        fcs[aid] = p
        a = ledger.agents[aid]
        cash, ef = p["balances"]["cash"]["value"], p["balances"]["efloat"]["value"]
        raw, _ = raw_forecast(ctx, aid, d, cash, ef)
        for kind in ("cash", "efloat"):
            cap_target = p["cash"]["capacity"] if kind == "cash" else p["efloat"]["capacity"]
            c = ar.Candidate(
                key=f"{aid}:{kind}", agent_id=aid, kind=kind, division=a["division"], tier=a["location_type"], cash=cash, efloat=ef,
                cap_cash=p["cash"]["capacity"], cap_efloat=p["efloat"]["capacity"], peak_cash=np.asarray(raw["peaks"]["cash"]),
                peak_efloat=np.asarray(raw["peaks"]["efloat"]), buffer_cash=p["cash"]["buffer"], buffer_efloat=p["efloat"]["buffer"],
                rule_amount=float(p[kind]["topup"]), trip_cost=float(e["trip_cost"][a["location_type"]]),
                min_order=ctx.rules["min_order_frac"] * cap_target)
            c.protect = bool(settings["protect_high_risk"] and p[kind]["status"] == "HIGH")
            c.risk_pct, c.status = float(p[kind]["risk_pct"]), p[kind]["status"]
            ar.prepare(c, v, lam)
            cands.append(c)
    return cands, fcs


def _lines(ctx: Ctx, d: date, cands: list[ar.Candidate], fcs: dict, amounts: dict, free: dict, locks: dict, v: float, lam: float) -> list[dict]:
    orders = {(o.agent_id, o.kind): o for o in ctx.db.scalars(select(Order).where(Order.plan_date == d.isoformat(), Order.status != "cancelled"))}
    out = []
    for c in cands:
        x, r = amounts[c.key], c.rule_amount
        if x <= 0 and r <= 0 and c.key not in locks:
            continue
        p = fcs[c.agent_id]
        sec = p[c.kind]
        o = orders.get((c.agent_id, c.kind))
        out.append(dict(
            key=c.key, agent_id=c.agent_id, division=c.division, tier=c.tier, kind=c.kind, meaning=KINDS[c.kind], rule_amount=round(r), amount=round(x),
            max_amount=round(c.xmax), reason=ar.reason(c, x, free.get(c.key, 0.0), ar.value_of(c, x, v, lam)), locked=c.key in locks, protected=c.protect,
            net_value=round(ar.value_of(c, x, v, lam)), value_if_rule=round(ar.value_of(c, min(r, c.xmax) if c.xmax else 0.0, v, lam)),
            trip_cost=round(c.trip_cost), risk_pct=sec["risk_pct"], status=p["status"], by_date=sec["topup_by_date"] or sec["next_working_day"],
            late=bool(sec["topup_late"]), order=order_dict(o) if o else None))
    out.sort(key=lambda r: (r["division"], r["agent_id"], r["kind"]))
    return out


def plan(ctx: Ctx, d: date, settings: dict | None = None, locks: dict[str, float] | None = None, curve: bool = True) -> dict:
    ctx.check_date(d)
    settings = settings or ctx.rules["allocation"]
    locks = {k: float(x) for k, x in (locks or {}).items()}
    cands, fcs = gather(ctx, d, settings)
    unknown = [k for k in locks if k not in {c.key for c in cands}]
    if unknown:
        raise ApiError(422, "validation_error", f"Unknown line: {unknown[0]}")
    if any(not np.isfinite(x) or x < 0 for x in locks.values()):
        raise ApiError(422, "validation_error", "Locked amounts must be zero or positive numbers")
    e, v, lam = _economics(ctx)
    sol = ar.solve(cands, settings, locks)
    note = None
    if sol["status"] != "optimal":                           # the limits cannot also protect every HIGH-risk agent: relax the protection first
        note = "protection_relaxed"
        sol = ar.solve(cands, settings, locks, protect=False)
    if sol["status"] != "optimal":                           # then the locks: show the plan without them
        note = "infeasible_locks"
        sol = ar.solve(cands, settings, protect=False)
        locks = {}
    cost_of_protection = None
    if settings["protect_high_risk"] and note is None and any(c.protect for c in cands):
        free_prot = ar.solve(cands, settings, locks, protect=False)
        if free_prot["status"] == "optimal":
            cost_of_protection = round(ar.metrics(cands, sol["amounts"], v, lam)["total_cost"] - ar.metrics(cands, free_prot["amounts"], v, lam)["total_cost"])
    amounts = sol["amounts"]
    free = ar.solve(cands, settings, locks, relax=True, protect=False)["amounts"]          # what the economics alone would do, ignoring budgets and trip limits
    rule = {c.key: min(c.rule_amount, c.xmax) if c.xmax else 0.0 for c in cands}
    none = {c.key: 0.0 for c in cands}
    simple = ar.simple_plan(cands, settings)
    totals = dict(rule=ar.metrics(cands, rule, v, lam, settings), simple=ar.metrics(cands, simple, v, lam, settings), optimised=ar.metrics(cands, amounts, v, lam, settings),
                  nothing=ar.metrics(cands, none, v, lam, settings), unconstrained=ar.metrics(cands, free, v, lam, settings))
    totals["rule"]["raw_net_cash"] = sum(c.rule_amount for c in cands if c.kind == "cash") - sum(c.rule_amount for c in cands if c.kind == "efloat")
    pts = []
    if curve:
        top = max(150_000.0, 1.3 * max(0.0, totals["rule"]["net_cash"]), 1.3 * settings["cash_budget"])
        for b in np.linspace(0, top, BUDGET_POINTS):
            s2 = {**settings, "cash_budget": float(b)}
            sol2 = ar.solve(cands, s2)
            if sol2["status"] != "optimal":
                sol2 = ar.solve(cands, s2, protect=False)
            m = ar.metrics(cands, sol2["amounts"], v, lam, s2)
            pts.append(dict(budget=round(float(b)), expected_unserved=round(m["expected_unserved"]), total_cost=round(m["total_cost"]), orders=m["orders"], net_cash=round(m["net_cash"])))
    rnd = lambda m: {k: (round(x) if isinstance(x, float) else x) for k, x in m.items()}
    return dict(
        date=d.isoformat(), settings=settings, status="optimal", note=note, cost_of_protection=cost_of_protection, lines=_lines(ctx, d, cands, fcs, amounts, free, locks, v, lam),
        totals={k: rnd(m) for k, m in totals.items()}, budget_curve=pts,
        saving_vs_rule=round(totals["rule"]["total_cost"] - totals["optimised"]["total_cost"]),
        saving_vs_simple=round(totals["simple"]["total_cost"] - totals["optimised"]["total_cost"]),
        unserved_avoided_vs_simple=round(totals["simple"]["expected_unserved"] - totals["optimised"]["expected_unserved"]),
        assumptions=dict(value_per_unserved_bdt=v, capital_rate_horizon=lam, horizon_days=ar.HORIZON_DAYS, trip_cost=e["trip_cost"], source="ROI & coverage assumptions (placeholders until upay supplies real figures)"),
        method="Expected unserved demand from the same Monte Carlo paths as the risk numbers; exact MILP over the whole network (HiGHS). Recommendations only.")


def approve(ctx: Ctx, actor: str, d: date, locks: dict[str, float] | None) -> dict:
    """Creates a proposed planning order for every optimised line that has no order yet today."""
    if d != ctx.sim_date:
        raise ApiError(422, "validation_error", "Only today's plan can be approved")
    p = plan(ctx, d, locks=locks, curve=False)
    created, skipped = [], []
    for ln in p["lines"]:
        if ln["amount"] <= 0:
            continue
        if ln["order"]:
            skipped.append(dict(key=ln["key"], order_id=ln["order"]["id"]))
            continue
        due = date.fromisoformat(ln["by_date"])
        due = max(due, ctx.sim_date)
        order_type = "emergency" if ln["status"] == "HIGH" and ln["late"] else "planned"
        created.append(create_order(ctx, actor, ln["agent_id"], ln["kind"], float(ln["amount"]), due, order_type, status="proposed", note="Optimised plan"))
    audit(ctx.db, actor, "allocation_approve", "allocation", d.isoformat(), dict(created=len(created), skipped=len(skipped), locks=locks or {}, saving_vs_rule=p["saving_vs_rule"]))
    ctx.db.commit()
    return dict(created=created, skipped=skipped, plan=plan(ctx, d, locks=locks, curve=False))
